import unittest
from unittest.mock import patch

import pdf_utils


GOOD_TEXT = """
Statement of Management's Responsibility
Management is responsible for the preparation and fair presentation of the
financial statements in accordance with Philippine Financial Reporting Standards.
"""

MORE_GOOD_TEXT = """
Statement of Management's Responsibility for Financial Statements
Management is responsible for preparing and presenting these annual financial
statements in accordance with Philippine Financial Reporting Standards.
The board confirms that internal controls support reliable financial reporting.
"""

POOR_TEXT = "|||| ||| 11 @@ ## %% ^^ ~~ ::: ;;; 00 11 /\/\/\/\ufffd\ufffd"


class DummyPage:
    rotation = 90


class OcrRotationTest(unittest.TestCase):
    def test_good_upright_ocr_is_kept_without_alternate_rotations(self):
        calls = []

        def fake_ocr(page, rotation):
            calls.append(rotation)
            return GOOD_TEXT, ""

        with patch.object(pdf_utils, "_ocr_page_text", side_effect=fake_ocr):
            effective, original, ocr, source, error = pdf_utils._apply_ocr_fallback(DummyPage(), "")

        self.assertEqual(effective, GOOD_TEXT.strip())
        self.assertEqual(original, "")
        self.assertEqual(ocr, GOOD_TEXT.strip())
        self.assertEqual(source, "OCR Fallback")
        self.assertEqual(error, "")
        self.assertEqual(calls, [90])

    def test_poor_baseline_selects_good_90_degree_candidate(self):
        outputs = {
            90: (POOR_TEXT, ""),
            0: (POOR_TEXT, ""),
            180: (POOR_TEXT, ""),
            270: (MORE_GOOD_TEXT, ""),
        }

        with patch.object(pdf_utils, "_ocr_page_text", side_effect=lambda page, rotation: outputs[rotation]):
            effective, original, ocr, source, error = pdf_utils._apply_ocr_fallback(DummyPage(), "")

        self.assertEqual(effective, MORE_GOOD_TEXT.strip())
        self.assertEqual(original, "")
        self.assertEqual(ocr, MORE_GOOD_TEXT.strip())
        self.assertEqual(source, "OCR Fallback")
        self.assertEqual(error, "")

    def test_poor_baseline_selects_good_270_degree_candidate(self):
        outputs = {
            90: (POOR_TEXT, ""),
            0: (POOR_TEXT, ""),
            180: (GOOD_TEXT, ""),
            270: (POOR_TEXT, ""),
        }

        with patch.object(pdf_utils, "_ocr_page_text", side_effect=lambda page, rotation: outputs[rotation]):
            effective, original, ocr, source, error = pdf_utils._apply_ocr_fallback(DummyPage(), "")

        self.assertEqual(effective, GOOD_TEXT.strip())
        self.assertEqual(original, "")
        self.assertEqual(ocr, GOOD_TEXT.strip())
        self.assertEqual(source, "OCR Fallback")
        self.assertEqual(error, "")

    def test_poor_baseline_and_all_poor_candidates_keep_best_available_text(self):
        best_poor_text = "abc def 123 !!! ???"
        outputs = {
            90: (POOR_TEXT, ""),
            0: (best_poor_text, ""),
            180: ("@@@ 111 !!!", ""),
            270: ("### 222 $$$", ""),
        }

        with patch.object(pdf_utils, "_ocr_page_text", side_effect=lambda page, rotation: outputs[rotation]):
            effective, original, ocr, source, error = pdf_utils._apply_ocr_fallback(DummyPage(), "")

        self.assertEqual(effective, best_poor_text)
        self.assertEqual(original, "")
        self.assertEqual(ocr, best_poor_text)
        self.assertEqual(source, "OCR Fallback")
        self.assertEqual(error, "")
        self.assertLess(pdf_utils._ocr_text_quality(ocr)["score"], pdf_utils.OCR_ACCEPTABLE_SCORE)

    def test_readable_text_layer_page_never_enters_ocr_rotation_selection(self):
        text_layer = "Readable text layer. " * 10

        with patch.object(pdf_utils, "_ocr_page_text") as ocr_page_text:
            effective, original, ocr, source, error = pdf_utils._apply_ocr_fallback(DummyPage(), text_layer)

        ocr_page_text.assert_not_called()
        self.assertEqual(effective, text_layer)
        self.assertEqual(original, text_layer)
        self.assertEqual(ocr, "")
        self.assertEqual(source, "Text Layer")
        self.assertEqual(error, "")

    def test_ocr_subprocess_or_render_failure_remains_safe(self):
        with patch.object(pdf_utils, "_ocr_page_text", return_value=("", "render failed")):
            effective, original, ocr, source, error = pdf_utils._apply_ocr_fallback(DummyPage(), "")

        self.assertEqual(effective, "")
        self.assertEqual(original, "")
        self.assertEqual(ocr, "")
        self.assertEqual(source, "Text Layer")
        self.assertEqual(error, "render failed")

    def test_existing_extracted_text_semantics_remain_correct(self):
        with patch.object(pdf_utils, "_ocr_page_text", return_value=(GOOD_TEXT, "")):
            effective, original, ocr, source, error = pdf_utils._apply_ocr_fallback(DummyPage(), "")

        page = {
            "text": effective,
            "extracted_text": effective,
            "original_text": original,
            "ocr_text": ocr,
            "extraction_source": source,
        }

        self.assertEqual(page["extracted_text"], page["ocr_text"])
        self.assertEqual(page["extraction_source"], "OCR Fallback")
        self.assertEqual(error, "")


if __name__ == "__main__":
    unittest.main()
