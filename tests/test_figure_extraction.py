import unittest

from extraction_engine import extract_figures_from_pages, select_preferred_figures
from normalization import parse_amount


PAGE_60 = """
DEL MONTE PHILIPPINES, INC. AND SUBSIDIARIES
CONSOLIDATED STATEMENTS OF COMPREHENSIVE INCOME
(In Thousands)
Years Ended April 30
2024 2023 2022
REVENUES (Notes 24) P38,749,105 P41,067,618 P36,556,457
GROSS INCOME 9,161,730 10,415,867 10,814,256
NET INCOME 2,604,867 3,708,363 4,893,776
OTHER COMPREHENSIVE INCOME (LOSS)
TOTAL COMPREHENSIVE INCOME P2,565,783 4,166,544 5,063,233
"""


class FigureExtractionTests(unittest.TestCase):
    def test_primary_income_rows_map_headers_to_values(self):
        figures = extract_figures_from_pages([{
            "page_number": 60,
            "page_type": "Statement of Comprehensive Income",
            "extracted_text": PAGE_60,
            "text_length": len(PAGE_60),
            "image_quality_flag": "Passed",
        }], [2024, 2023, 2022])
        by_key = {(row["normalized_label"], row["fiscal_year"]): row for row in figures}
        self.assertEqual(by_key[("revenue", 2024)]["displayed_value"], "38,749,105")
        self.assertEqual(by_key[("net_income", 2024)]["displayed_value"], "2,604,867")
        self.assertEqual(by_key[("gross_income", 2024)]["normalized_peso_value"], 9161730000.0)
        self.assertEqual(by_key[("total_comprehensive_income", 2024)]["normalized_peso_value"], 2565783000.0)
        self.assertNotIn("2023", [row["displayed_value"] for row in figures if row["fiscal_year"] == 2024])

    def test_parenthesized_amount_remains_negative(self):
        self.assertEqual(parse_amount("(63,820)", "Thousands"), -63820000.0)

    def test_preferred_duplicate_uses_primary_statement(self):
        figures = [{
            "id": 1,
            "page_number": 59,
            "statement_type": "Statement of Financial Position / Balance Sheet",
            "normalized_label": "total_equity",
            "fiscal_year": 2024,
            "normalized_peso_value": 14745624000.0,
        }, {
            "id": 2,
            "page_number": 143,
            "statement_type": "Notes to Financial Statements",
            "normalized_label": "total_equity",
            "fiscal_year": 2024,
            "normalized_peso_value": 14745624000.0,
        }]
        preferred = select_preferred_figures(figures)
        self.assertEqual(len(preferred), 1)
        self.assertEqual(preferred[0]["id"], 1)


if __name__ == "__main__":
    unittest.main()
