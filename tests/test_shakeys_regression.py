import unittest

from extraction_engine import extract_figures_from_pages, select_preferred_figures
from validation_engine import detect_afs_reporting_years, evaluate_afs_completeness, page_scope


SHAKEYS_SFP = """
SHAKEY'S PIZZA ASIA VENTURES INC. AND SUBSIDIARIES
CONSOLIDATED STATEMENTS OF FINANCIAL POSITION
December 31
2022 2021
ASSETS
Current Assets
Cash (Notes 6, 8 and 31) P989,578,790 P485,414,521
Total Current Assets 3,854,643,595 2,129,830,903
Total Noncurrent Assets 13,853,774,682 10,504,882,025
TOTAL ASSETS P17,708,418,277 P12,634,712,928
LIABILITIES AND EQUITY
Total Liabilities 10,662,641,171 6,453,925,406
Total Equity 7,045,777,106 6,180,787,522
"""

SHAKEYS_INCOME = """
SHAKEY'S PIZZA ASIA VENTURES INC. AND SUBSIDIARIES
CONSOLIDATED STATEMENTS OF COMPREHENSIVE INCOME
Years Ended December 31
2022 2021 2020
REVENUE FROM CONTRACTS WITH CUSTOMERS P10,142,024,578 P5,480,427,588 P5,296,771,546
COST OF SALES (7,546,508,401) (4,206,711,163) (4,364,157,309)
GROSS INCOME 2,595,516,177 1,273,716,425 932,614,237
INCOME (LOSS) BEFORE INCOME TAX 1,098,414,938 230,679,570 (368,511,175)
NET INCOME (LOSS) 874,402,081 122,980,158 (253,589,288)
OTHER COMPREHENSIVE INCOME (LOSS)
TOTAL COMPREHENSIVE INCOME P915,502,389 P180,097,945 (P268,829,149)
"""

SHAKEYS_EQUITY = """
SHAKEY'S PIZZA ASIA VENTURES INC. AND SUBSIDIARIES
CONSOLIDATED STATEMENTS OF CHANGES IN EQUITY
FOR THE YEARS ENDED DECEMBER 31, 2022 AND 2021
Capital Stock Additional Paid-in Capital Retained Earnings Other Components of Equity Total
Balances at January 1, 2022 P1,683,760,178 P2,451,116,470 P2,053,473,219 (P7,562,345) P6,180,787,522
Total comprehensive income - - 874,402,081 41,100,308 915,502,389
Balances at December 31, 2022 P1,683,760,178 P2,451,116,470 P2,877,362,495 P33,537,963 P7,045,777,106
"""

PARENT_SFP = """
SHAKEY'S PIZZA ASIA VENTURES INC.
PARENT COMPANY STATEMENTS OF FINANCIAL POSITION
2022 2021
Cash and Cash Equivalents 385,015,940 309,829,604
TOTAL ASSETS 15,519,834,365 12,042,281,987
"""


class ShakeysRegressionTests(unittest.TestCase):
    def test_reporting_years_ignore_signing_and_historical_dates(self):
        pages = [
            {"page_number": 2, "page_type": "Statement of Management's Responsibility", "extracted_text": "Signed this day of April, 2023"},
            {"page_number": 11, "page_type": "Statement of Comprehensive Income", "extracted_text": SHAKEYS_INCOME},
            {"page_number": 20, "page_type": "Other / Unclassified", "extracted_text": "Historical acquisition occurred in 2019."},
        ]
        self.assertEqual(detect_afs_reporting_years(pages), [2022, 2021, 2020])

    def test_scope_classification(self):
        self.assertEqual(page_scope(SHAKEYS_SFP), "consolidated")
        self.assertEqual(page_scope(PARENT_SFP), "parent")

    def test_completeness_uses_consolidated_primary_pages(self):
        pages = [
            {"page_number": 10, "page_type": "Statement of Financial Position / Balance Sheet", "extracted_text": SHAKEYS_SFP},
            {"page_number": 11, "page_type": "Statement of Comprehensive Income", "extracted_text": SHAKEYS_INCOME},
            {"page_number": 12, "page_type": "Statement of Changes in Equity / Fund Balance", "extracted_text": SHAKEYS_EQUITY},
            {"page_number": 31, "page_type": "Other / Unclassified", "extracted_text": "Revenue Regulations No. 25-2020 amended Section 4."},
            {"page_number": 87, "page_type": "Statement of Financial Position / Balance Sheet", "extracted_text": PARENT_SFP},
        ]
        result = evaluate_afs_completeness(pages, {"company_name": "Shakey's Pizza Asia Ventures Inc. and Subsidiaries"})
        components = {item["component"]: item for item in result["components"]}
        self.assertEqual(components["Statement of Financial Position / Balance Sheet"]["page_numbers"], [10])
        self.assertEqual(components["Statement of Profit or Loss / Statement of Income"]["page_numbers"], [11])
        self.assertEqual(components["Other Comprehensive Income"]["page_numbers"], [11])
        self.assertEqual(components["Statement of Changes in Equity"]["page_numbers"], [12])

    def test_figure_extraction_and_preferred_scope(self):
        pages = [
            {"page_number": 10, "page_type": "Statement of Financial Position / Balance Sheet", "extracted_text": SHAKEYS_SFP, "text_length": len(SHAKEYS_SFP), "image_quality_flag": "Passed"},
            {"page_number": 11, "page_type": "Statement of Comprehensive Income", "extracted_text": SHAKEYS_INCOME, "text_length": len(SHAKEYS_INCOME), "image_quality_flag": "Passed"},
            {"page_number": 31, "page_type": "Other / Unclassified", "extracted_text": "Revenue Regulations No. 25-2020 amended Section 4.", "text_length": 60, "image_quality_flag": "Passed"},
            {"page_number": 87, "page_type": "Statement of Financial Position / Balance Sheet", "extracted_text": PARENT_SFP, "text_length": len(PARENT_SFP), "image_quality_flag": "Passed"},
        ]
        figures = select_preferred_figures(extract_figures_from_pages(pages, [2022, 2021, 2020]))
        by_key = {(row["normalized_label"], row["fiscal_year"]): row for row in figures}
        self.assertEqual(by_key[("revenue", 2022)]["normalized_peso_value"], 10142024578.0)
        self.assertEqual(by_key[("gross_income", 2022)]["normalized_peso_value"], 2595516177.0)
        self.assertEqual(by_key[("net_income", 2022)]["normalized_peso_value"], 874402081.0)
        self.assertEqual(by_key[("total_comprehensive_income", 2022)]["normalized_peso_value"], 915502389.0)
        self.assertEqual(by_key[("total_assets", 2022)]["normalized_peso_value"], 17708418277.0)
        self.assertEqual(by_key[("total_liabilities", 2022)]["normalized_peso_value"], 10662641171.0)
        self.assertEqual(by_key[("total_equity", 2022)]["normalized_peso_value"], 7045777106.0)
        self.assertEqual(by_key[("cash_and_cash_equivalents", 2022)]["normalized_peso_value"], 989578790.0)
        revenue_values = [row["displayed_value"] for row in figures if row["normalized_label"] == "revenue"]
        self.assertNotIn("-2020", revenue_values)
        self.assertNotIn("4", revenue_values)


if __name__ == "__main__":
    unittest.main()
