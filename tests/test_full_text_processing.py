import unittest

from extraction_engine import extract_figures_from_pages
from validation_engine import _processing_text


class FullTextProcessingTest(unittest.TestCase):
    def test_processing_text_prefers_extracted_text_over_preview(self):
        page = {
            "extracted_text": "complete effective text",
            "text_preview": "truncated preview",
        }

        self.assertEqual(_processing_text(page), "complete effective text")

    def test_figure_extraction_scans_text_after_preview_limit(self):
        page = {
            "page_number": 1,
            "page_type": "Statement of Income",
            "text_preview": "x" * 2000,
            "extracted_text": ("x" * 2100) + " Gross Revenue 2025 1,234,567",
        }

        figures = extract_figures_from_pages([page], [2025])

        self.assertEqual(len(figures), 1)
        self.assertEqual(figures[0]["raw_label"], "Gross Revenue")
        self.assertEqual(figures[0]["displayed_value"], "1,234,567")

    def test_processing_text_falls_back_without_extracted_text(self):
        page = {
            "text_preview": "legacy preview text",
        }

        self.assertEqual(_processing_text(page), "legacy preview text")


if __name__ == "__main__":
    unittest.main()
