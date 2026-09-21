import unittest

from validation_engine import evaluate_afs_completeness


def component(result, name):
    return next(item for item in result["components"] if item["component"] == name)


class AfsClassificationTests(unittest.TestCase):
    def test_comprehensive_income_satisfies_income_and_oci(self):
        result = evaluate_afs_completeness([{
            "page_number": 60,
            "page_type": "Statement of Comprehensive Income",
            "extracted_text": """
CONSOLIDATED STATEMENTS OF COMPREHENSIVE INCOME
Years Ended April 30
2024 2023 2022
REVENUES P38,749,105 P41,067,618 P36,556,457
GROSS INCOME 9,161,730 10,415,867 10,814,256
NET INCOME 2,604,867 3,708,363 4,893,776
OTHER COMPREHENSIVE INCOME (LOSS)
TOTAL COMPREHENSIVE INCOME P2,565,783 P4,166,544 P5,063,233
""",
        }])
        self.assertEqual(component(result, "Statement of Profit or Loss / Statement of Income")["status"], "Detected")
        self.assertEqual(component(result, "Other Comprehensive Income")["status"], "Detected")

    def test_notes_to_consolidated_financial_statements_recognized(self):
        result = evaluate_afs_completeness([{
            "page_number": 64,
            "page_type": "Notes to Financial Statements",
            "extracted_text": "DEL MONTE PHILIPPINES, INC. AND SUBSIDIARIES\nNOTES TO THE CONSOLIDATED FINANCIAL STATEMENTS\n1. Reporting Entity",
        }])
        self.assertEqual(component(result, "Notes to Financial Statements")["status"], "Detected")

    def test_weak_reference_does_not_satisfy_component(self):
        result = evaluate_afs_completeness([{
            "page_number": 86,
            "page_type": "Other / Unclassified",
            "extracted_text": "See Statement of Changes in Equity for the related movement.",
        }])
        self.assertEqual(component(result, "Statement of Changes in Equity")["status"], "Missing")


if __name__ == "__main__":
    unittest.main()
