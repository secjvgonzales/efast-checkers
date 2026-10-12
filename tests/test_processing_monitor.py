import unittest

from streamlit.testing.v1 import AppTest

from pages.upload_intake import (
    PROCESSING_STAGE_ORDER,
    _estimated_duration,
    _format_elapsed,
    _mark_analysis_requested,
    _processing_snapshot,
    _set_post_analysis_navigation,
)


def render_active_processing_monitor():
    from pages.upload_intake import ProcessingMonitor

    monitor = ProcessingMonitor("AFS", 2 * 1024 * 1024)
    monitor.start("prepare")
    monitor.complete("prepare")
    monitor.start("extract")


def render_completed_processing_monitor():
    from pages.upload_intake import PROCESSING_STAGE_ORDER, ProcessingMonitor

    monitor = ProcessingMonitor("GIS", 2 * 1024 * 1024)
    for stage in PROCESSING_STAGE_ORDER[:-1]:
        monitor.start(stage)
        monitor.complete(stage)
    monitor.start("review")
    monitor.finish(["PDF processed", "12 pages analyzed", "Reviewer results prepared"])


class ProcessingMonitorStateTests(unittest.TestCase):
    def test_initial_afs_state_is_pending_with_zero_progress(self):
        snapshot = _processing_snapshot("AFS")

        self.assertEqual(0, snapshot["progress"])
        self.assertTrue(all(row["state"] == "pending" for row in snapshot["rows"]))

    def test_active_stage_does_not_advance_progress_until_completed(self):
        snapshot = _processing_snapshot("GIS", ["prepare"], active_stage="extract")

        self.assertEqual(10, snapshot["progress"])
        extraction_rows = [row for row in snapshot["rows"] if row["stage"] == "extract"]
        self.assertTrue(extraction_rows)
        self.assertTrue(all(row["state"] == "active" for row in extraction_rows))

    def test_all_real_boundaries_reach_one_hundred_percent(self):
        snapshot = _processing_snapshot("AFS", PROCESSING_STAGE_ORDER)

        self.assertEqual(100, snapshot["progress"])
        self.assertTrue(all(row["state"] == "completed" for row in snapshot["rows"]))

    def test_review_stage_does_not_complete_prematurely(self):
        snapshot = _processing_snapshot(
            "AFS",
            PROCESSING_STAGE_ORDER[:-1],
            active_stage="review",
        )

        self.assertEqual(96, snapshot["progress"])
        review_rows = [row for row in snapshot["rows"] if row["stage"] == "review"]
        self.assertTrue(all(row["state"] == "active" for row in review_rows))

    def test_failed_stage_is_marked_as_error(self):
        snapshot = _processing_snapshot("AFS", ["prepare", "extract"], failed_stage="analyze")

        failed_rows = [row for row in snapshot["rows"] if row["stage"] == "analyze"]
        self.assertTrue(failed_rows)
        self.assertTrue(all(row["state"] == "error" for row in failed_rows))
        self.assertEqual(32, snapshot["progress"])

    def test_estimate_expands_for_large_or_ocr_documents(self):
        self.assertEqual((30, 90), _estimated_duration(2 * 1024 * 1024))
        self.assertEqual((60, 180), _estimated_duration(2 * 1024 * 1024, ocr_used=True))
        self.assertEqual((90, 300), _estimated_duration(30 * 1024 * 1024))

    def test_elapsed_format_uses_real_seconds(self):
        self.assertEqual("00:00", _format_elapsed(0))
        self.assertEqual("01:14", _format_elapsed(74.9))

    def test_duplicate_request_is_rejected_while_processing(self):
        state = {}

        self.assertTrue(_mark_analysis_requested(state))
        self.assertFalse(_mark_analysis_requested(state))
        self.assertTrue(state["_intake_processing"])
        self.assertTrue(state["_intake_run_requested"])

    def test_active_monitor_renders_without_exception(self):
        app = AppTest.from_function(render_active_processing_monitor)

        app.run(timeout=30)

        self.assertEqual([], list(app.exception))

    def test_completed_monitor_renders_without_exception(self):
        app = AppTest.from_function(render_completed_processing_monitor)

        app.run(timeout=30)

        self.assertEqual([], list(app.exception))

    def test_document_review_navigation_state(self):
        state = {}

        _set_post_analysis_navigation(state, 42, "Document Review", "GIS")

        self.assertEqual(42, state["active_document_id"])
        self.assertEqual("Document Review", state["_current_page"])
        self.assertEqual("GIS", state["review_context"])

    def test_afs_figures_navigation_state(self):
        state = {}

        _set_post_analysis_navigation(state, 17, "AFS Figures Extraction Review", "AFS")

        self.assertEqual(17, state["active_document_id"])
        self.assertEqual("AFS Figures Extraction Review", state["_current_page"])
        self.assertEqual("AFS", state["review_context"])


if __name__ == "__main__":
    unittest.main()
