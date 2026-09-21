import unittest

from confidence import calculate_figure_confidence


class ConfidenceTests(unittest.TestCase):
    def test_year_token_value_is_capped(self):
        result = calculate_figure_confidence({
            "raw_label": "Revenue",
            "normalized_label": "revenue",
            "fiscal_year": 2024,
            "displayed_value": "2023",
            "normalized_peso_value": 2023.0,
            "unit_basis": "Pesos",
            "source_snippet": "Revenue 2024 2023 2022",
            "statement_type": "Other / Unclassified",
        }, {"text_length": 200, "image_quality_flag": "Passed", "extracted_text": "Revenue 2024 2023 2022"})
        self.assertLessEqual(result["score"], 49)
        self.assertEqual(result["initial_review_status"], "Check Source")

    def test_primary_source_scores_better_than_unclassified(self):
        figure = {
            "raw_label": "Revenue",
            "normalized_label": "revenue",
            "fiscal_year": 2024,
            "displayed_value": "38,749,105",
            "normalized_peso_value": 38749105000.0,
            "unit_basis": "Thousands",
            "source_snippet": "REVENUES 2024 38,749,105",
        }
        page = {"text_length": 250, "image_quality_flag": "Passed", "extracted_text": "REVENUES 2024 38,749,105"}
        primary = calculate_figure_confidence({**figure, "statement_type": "Statement of Comprehensive Income"}, page)
        weak = calculate_figure_confidence({**figure, "statement_type": "Other / Unclassified"}, page)
        self.assertGreater(primary["score"], weak["score"])


if __name__ == "__main__":
    unittest.main()
