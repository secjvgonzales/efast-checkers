import unittest

import pandas as pd
from streamlit.testing.v1 import AppTest

from pages.figures_review import _prepare_editable_figures


def render_seeded_figures_review():
    import streamlit as st

    from db import init_db
    from pages.figures_review import render
    from storage import ensure_demo_document, seed_company_master

    init_db()
    seed_company_master()
    st.session_state["active_document_id"] = ensure_demo_document("AFS")
    st.session_state["review_context"] = "AFS"
    st.data_editor = lambda data, **kwargs: data
    st.dataframe = lambda data, **kwargs: None
    render()


def render_figures_review_without_rows():
    import streamlit as st

    from db import init_db
    import pages.figures_review as figures_review
    from storage import ensure_demo_document, seed_company_master

    init_db()
    seed_company_master()
    st.session_state["active_document_id"] = ensure_demo_document("AFS")
    st.session_state["review_context"] = "AFS"
    figures_review.get_figures = lambda document_id: []
    figures_review.render()


class FiguresReviewRenderTests(unittest.TestCase):
    def test_editable_figures_are_initialized_before_display_filters(self):
        row = {
            "id": 7,
            "page_number": 2,
            "statement_type": "Statement of Financial Position",
            "raw_label": "Total Assets",
            "normalized_label": "total_assets",
            "fiscal_year": 2025,
            "displayed_value": "1,000",
            "normalized_peso_value": 1000.0,
            "unit_basis": "Pesos",
            "source_snippet": "Total Assets 2025 1,000",
            "confidence": "High",
            "review_status": "Needs Review",
            "reviewer_edited": 0,
            "reviewed_value": None,
            "computed_confidence_score": 95,
            "confidence_classification": "High",
        }
        figures = pd.DataFrame([row])

        editable = _prepare_editable_figures(
            figures,
            figures,
            2025,
            lambda figure: figure["review_status"],
            selected_status_filter="Needs Review",
            figure_search="assets",
        )

        self.assertEqual([7], editable["id"].tolist())
        self.assertEqual("Current", editable.iloc[0]["year_role"])
        self.assertEqual("95% · High", editable.iloc[0]["conf_display"])

    def test_seeded_afs_figures_page_renders_without_exception(self):
        app = AppTest.from_function(render_seeded_figures_review)

        app.run(timeout=30)

        self.assertEqual([], list(app.exception))

    def test_no_figures_state_renders_without_exception(self):
        app = AppTest.from_function(render_figures_review_without_rows)

        app.run(timeout=30)

        self.assertEqual([], list(app.exception))
        self.assertTrue(any("No supported financial figures" in warning.value for warning in app.warning))


if __name__ == "__main__":
    unittest.main()
