import unittest

from validation_engine import detect_afs_reporting_years


class PeriodDetectionTests(unittest.TestCase):
    def test_authoritative_statement_period_detected(self):
        pages = [{
            "page_number": 60,
            "page_type": "Statement of Comprehensive Income",
            "extracted_text": """
DEL MONTE PHILIPPINES, INC. AND SUBSIDIARIES
CONSOLIDATED STATEMENTS OF COMPREHENSIVE INCOME
(In Thousands)
Years Ended April 30
2024 2023 2022
REVENUES P38,749,105 P41,067,618 P36,556,457
""",
        }]
        self.assertEqual(detect_afs_reporting_years(pages), [2024, 2023, 2022])

    def test_incidental_future_years_do_not_establish_period(self):
        pages = [{
            "page_number": 58,
            "page_type": "Independent Auditor's Report",
            "extracted_text": "BIR Accreditation No. 08-001998 valid until November 6, 2025",
        }, {
            "page_number": 115,
            "page_type": "Other / Unclassified",
            "extracted_text": "Long-term loan due August 3, 2025 and commitments expected in fiscal year 2026.",
        }]
        self.assertEqual(detect_afs_reporting_years(pages), [])


if __name__ == "__main__":
    unittest.main()
