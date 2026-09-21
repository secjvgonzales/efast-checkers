import unittest

from extraction_engine import extract_figures_from_pages
from normalization import detect_unit_basis, parse_amount


SHELL_SFP_TEXT = """
Statement of Financial Position
As at December 31, 2025 and 2024
(All amounts in thousand Philippine pesos)

                                      2025          2024
Total Assets                   118,022,680   117,107,764
Total Liabilities               83,249,128    84,926,922
Total Equity                    34,773,552    32,180,842
"""

REAL_SHELL_PAGE_16_TEXT = """
Statement of Financial Position
(All amounts in thousand Philippine pesos, except par value per share)

2025
2024

TOTAL ASSETS

118,022,680 117,107,764
TOTAL LIABILITIES

83,249,128
84,926,922
Total Equity
34,773,552
32,180,842
"""

LIABILITIES_AND_EQUITY_TEXT = """
Statement of Financial Position
(All amounts in thousand Philippine pesos)

2025
2024

TOTAL LIABILITIES
83,249,128
84,926,922

TOTAL LIABILITIES AND EQUITY
118,022,680 117,107,764
"""

PRIMARY_STATEMENTS_SFP_TEXT = """
SHELL PILIPINAS CORPORATION
STATEMENTS OF FINANCIAL POSITION
(All amounts in thousand Philippine pesos)

2025
2024

TOTAL ASSETS
118,022,680 117,107,764
TOTAL LIABILITIES
83,249,128
84,926,922
Total Equity
34,773,552
32,180,842
"""

NOTES_CAPITAL_MANAGEMENT_TEXT = """
SHELL PILIPINAS CORPORATION
NOTES TO THE FINANCIAL STATEMENTS
For the years ended December 31

28. Financial risk management (continued)
28.2 Capital management
The Company monitors capital using balances from the statement of financial position.

2025
2024
Total equity (excluding other reserves)
33,553,988
30,913,454
"""


def sfp_page(text=SHELL_SFP_TEXT, page_type="Statement of Financial Position / Balance Sheet"):
    return {
        "page_number": 10,
        "page_type": page_type,
        "extracted_text": text,
    }


def figures_by_label_year(figures):
    return {
        (figure["normalized_label"], int(figure["fiscal_year"])): figure
        for figure in figures
    }


class SfpRowExtractionTest(unittest.TestCase):
    def test_primary_statement_heading_allows_structured_sfp_extraction(self):
        figures = extract_figures_from_pages([sfp_page(PRIMARY_STATEMENTS_SFP_TEXT)], [2025, 2024])

        self.assertEqual(len(figures), 6)

    def test_notes_heading_rejects_structured_sfp_even_with_later_statement_reference(self):
        figures = extract_figures_from_pages([sfp_page(NOTES_CAPITAL_MANAGEMENT_TEXT)], [2025, 2024])

        self.assertEqual(figures, [])

    def test_real_page_67_style_notes_capital_management_does_not_emit_total_equity(self):
        figures = extract_figures_from_pages([sfp_page(NOTES_CAPITAL_MANAGEMENT_TEXT)], [2025, 2024])

        self.assertEqual([
            figure for figure in figures
            if figure["normalized_label"] == "total_equity"
        ], [])

    def test_generic_fallback_rejects_year_header_as_value(self):
        page = {
            "page_number": 92,
            "page_type": "Notes to Financial Statements",
            "extracted_text": """
            Revenue
            2025
            2024
            Performance obligations satisfied
            569,651
            569,773
            """,
        }

        figures = extract_figures_from_pages([page], [2025, 2024])

        self.assertNotIn("2024", [figure["displayed_value"] for figure in figures])
        self.assertNotIn("2025", [figure["displayed_value"] for figure in figures])

    def test_real_layout_separate_year_lines_map_in_order(self):
        figures = extract_figures_from_pages([sfp_page(REAL_SHELL_PAGE_16_TEXT)], [2025, 2024])
        assets = [
            figure for figure in figures
            if figure["normalized_label"] == "total_assets"
        ]

        self.assertEqual([figure["fiscal_year"] for figure in assets], [2025, 2024])

    def test_real_layout_total_assets_values_after_label(self):
        figures = extract_figures_from_pages([sfp_page(REAL_SHELL_PAGE_16_TEXT)], [2025, 2024])
        indexed = figures_by_label_year(figures)

        self.assertEqual(indexed[("total_assets", 2025)]["displayed_value"], "118,022,680")
        self.assertEqual(indexed[("total_assets", 2024)]["displayed_value"], "117,107,764")

    def test_real_layout_total_liabilities_values_on_following_lines(self):
        figures = extract_figures_from_pages([sfp_page(REAL_SHELL_PAGE_16_TEXT)], [2025, 2024])
        indexed = figures_by_label_year(figures)

        self.assertEqual(indexed[("total_liabilities", 2025)]["displayed_value"], "83,249,128")
        self.assertEqual(indexed[("total_liabilities", 2024)]["displayed_value"], "84,926,922")

    def test_real_layout_total_equity_values_after_label(self):
        figures = extract_figures_from_pages([sfp_page(REAL_SHELL_PAGE_16_TEXT)], [2025, 2024])
        indexed = figures_by_label_year(figures)

        self.assertEqual(indexed[("total_equity", 2025)]["displayed_value"], "34,773,552")
        self.assertEqual(indexed[("total_equity", 2024)]["displayed_value"], "32,180,842")

    def test_real_layout_emits_exactly_six_rows_for_two_years(self):
        figures = extract_figures_from_pages([sfp_page(REAL_SHELL_PAGE_16_TEXT)], [2025, 2024])

        self.assertEqual(len(figures), 6)

    def test_real_layout_emits_exactly_three_rows_for_current_year_only(self):
        figures = extract_figures_from_pages([sfp_page(REAL_SHELL_PAGE_16_TEXT)], [2025])

        self.assertEqual(len(figures), 3)
        self.assertEqual({int(figure["fiscal_year"]) for figure in figures}, {2025})

    def test_real_layout_unit_basis_is_thousands(self):
        figures = extract_figures_from_pages([sfp_page(REAL_SHELL_PAGE_16_TEXT)], [2025, 2024])

        self.assertEqual({figure["unit_basis"] for figure in figures}, {"Thousands"})

    def test_real_layout_normalized_peso_values(self):
        figures = extract_figures_from_pages([sfp_page(REAL_SHELL_PAGE_16_TEXT)], [2025, 2024])
        indexed = figures_by_label_year(figures)

        self.assertEqual(indexed[("total_assets", 2025)]["normalized_peso_value"], 118022680000)
        self.assertEqual(indexed[("total_assets", 2024)]["normalized_peso_value"], 117107764000)
        self.assertEqual(indexed[("total_liabilities", 2025)]["normalized_peso_value"], 83249128000)
        self.assertEqual(indexed[("total_liabilities", 2024)]["normalized_peso_value"], 84926922000)
        self.assertEqual(indexed[("total_equity", 2025)]["normalized_peso_value"], 34773552000)
        self.assertEqual(indexed[("total_equity", 2024)]["normalized_peso_value"], 32180842000)

    def test_generic_fallback_rejects_non_numeric_year_following_tokens(self):
        junk_tokens = ["are", "to", "issued", "Days", "consist", "Performance"]
        pages = [
            {
                "page_number": index + 40,
                "page_type": "Notes to Financial Statements",
                "extracted_text": f"Notes\nRevenue 2025 {token}",
            }
            for index, token in enumerate(junk_tokens)
        ]

        self.assertEqual(extract_figures_from_pages(pages, [2025]), [])

    def test_total_liabilities_does_not_match_total_liabilities_and_equity(self):
        figures = extract_figures_from_pages([sfp_page(LIABILITIES_AND_EQUITY_TEXT)], [2025, 2024])
        liabilities = [
            figure for figure in figures
            if figure["normalized_label"] == "total_liabilities"
        ]

        self.assertEqual(len(liabilities), 2)
        indexed = figures_by_label_year(liabilities)
        self.assertEqual(indexed[("total_liabilities", 2025)]["displayed_value"], "83,249,128")
        self.assertEqual(indexed[("total_liabilities", 2024)]["displayed_value"], "84,926,922")

    def test_notes_page_fallback_does_not_emit_core_sfp_labels(self):
        page = {
            "page_number": 67,
            "page_type": "Notes to Financial Statements",
            "extracted_text": "Notes\nTotal Equity 2025 33,553,988 2024 30,913,454",
        }

        figures = extract_figures_from_pages([page], [2025, 2024])

        self.assertEqual([
            figure for figure in figures
            if figure["normalized_label"] == "total_equity"
        ], [])

    def test_shell_style_total_assets_comparative_row(self):
        figures = extract_figures_from_pages([sfp_page()], [2025, 2024])
        indexed = figures_by_label_year(figures)

        self.assertEqual(indexed[("total_assets", 2025)]["displayed_value"], "118,022,680")
        self.assertEqual(indexed[("total_assets", 2024)]["displayed_value"], "117,107,764")

    def test_shell_style_total_liabilities_comparative_row(self):
        figures = extract_figures_from_pages([sfp_page()], [2025, 2024])
        indexed = figures_by_label_year(figures)

        self.assertEqual(indexed[("total_liabilities", 2025)]["displayed_value"], "83,249,128")
        self.assertEqual(indexed[("total_liabilities", 2024)]["displayed_value"], "84,926,922")

    def test_shell_style_total_equity_comparative_row(self):
        figures = extract_figures_from_pages([sfp_page()], [2025, 2024])
        indexed = figures_by_label_year(figures)

        self.assertEqual(indexed[("total_equity", 2025)]["displayed_value"], "34,773,552")
        self.assertEqual(indexed[("total_equity", 2024)]["displayed_value"], "32,180,842")

    def test_singular_thousand_unit_detection(self):
        self.assertEqual(detect_unit_basis("All amounts in thousand Philippine pesos"), "Thousands")

    def test_thousands_normalized_value(self):
        self.assertEqual(parse_amount("118,022,680", "Thousands"), 118022680000)

    def test_parentheses_negative_parsing_remains_correct(self):
        self.assertEqual(parse_amount("(1,234)", "Thousands"), -1234000)

    def test_only_requested_current_year_is_emitted(self):
        figures = extract_figures_from_pages([sfp_page()], [2025])
        indexed = figures_by_label_year(figures)

        self.assertIn(("total_assets", 2025), indexed)
        self.assertNotIn(("total_assets", 2024), indexed)
        self.assertNotIn(("total_liabilities", 2024), indexed)
        self.assertNotIn(("total_equity", 2024), indexed)

    def test_notes_page_does_not_use_structured_sfp_row_extractor(self):
        figures = extract_figures_from_pages(
            [sfp_page(page_type="Notes to Financial Statements")],
            [2025, 2024],
        )

        self.assertEqual(figures, [])

    def test_existing_regex_fallback_still_works(self):
        page = {
            "page_number": 15,
            "page_type": "Statement of Income",
            "extracted_text": "Statement of Income\nGross Revenue 2025 1,234,567",
        }

        figures = extract_figures_from_pages([page], [2025])

        self.assertEqual(len(figures), 1)
        self.assertEqual(figures[0]["raw_label"], "Gross Revenue")
        self.assertEqual(figures[0]["displayed_value"], "1,234,567")


if __name__ == "__main__":
    unittest.main()
