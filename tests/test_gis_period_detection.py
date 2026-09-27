import unittest

from gis_extraction_engine import detect_gis_reporting_year
from validation_engine import _gis_meeting_validation


class GisPeriodDetectionTests(unittest.TestCase):
    def test_reporting_year_from_strong_heading(self):
        item = detect_gis_reporting_year([{
            "page_number": 1,
            "page_type": "Corporate / Profile / Meeting Information",
            "extracted_text": "AMENDED GENERAL INFORMATION SHEET FOR THE YEAR 2025 Fiscal Year End December 31",
            "image_quality_flag": "Passed",
        }])

        self.assertEqual(item["value_text"], "2025")
        self.assertEqual(item["confidence_label"], "High")

    def test_fiscal_and_meeting_dates_do_not_become_reporting_year(self):
        item = detect_gis_reporting_year([{
            "page_number": 1,
            "page_type": "Corporate / Profile / Meeting Information",
            "extracted_text": "Fiscal Year End December 31, 2025. Actual Date of Annual Meeting April 15, 2025. Series of 2026.",
            "image_quality_flag": "Passed",
        }])

        self.assertIsNone(item)

    def test_labeled_reporting_year_is_fallback(self):
        item = detect_gis_reporting_year([{
            "page_number": 1,
            "page_type": "Corporate / Profile / Meeting Information",
            "extracted_text": "Corporate Name: Demo Corp. GIS Year: 2024. Notary Public Series of 2025.",
            "image_quality_flag": "Passed",
        }])

        self.assertEqual(item["value_text"], "2024")

    def test_multiline_amended_gis_heading_is_authoritative(self):
        item = detect_gis_reporting_year([{
            "page_number": 1,
            "page_type": "Corporate / Profile / Meeting Information",
            "extracted_text": "AMENDED GENERAL INFORMATION SHEET (GIS)\nFOR THE YEAR: 2025",
            "image_quality_flag": "Passed",
        }])

        self.assertEqual(item["value_text"], "2025")

    def test_actual_annual_meeting_short_date_matches_intake(self):
        result = _gis_meeting_validation([{
            "page_number": 1,
            "page_type": "Corporate / Profile / Meeting Information",
            "extracted_text": "ACTUAL DATE OF ANNUAL MEETING: 24-Apr-25 Fiscal Year End: December 31",
        }], {"submission_type": "Annual Meeting", "period_covered": "2025-04-24"})

        self.assertEqual(result["status"], "Passed")

    def test_fiscal_year_end_does_not_substitute_for_meeting_date(self):
        result = _gis_meeting_validation([{
            "page_number": 1,
            "page_type": "Corporate / Profile / Meeting Information",
            "extracted_text": "Fiscal Year End: December 31, 2025",
        }], {"submission_type": "Annual Meeting", "period_covered": "2025-05-27"})

        self.assertEqual(result["status"], "Needs Review")

    def test_generic_no_meeting_instruction_does_not_override_actual_date(self):
        result = _gis_meeting_validation([{
            "page_number": 1,
            "page_type": "Corporate / Profile / Meeting Information",
            "extracted_text": "IF NO MEETING IS HELD, file a new GIS. ACTUAL DATE OF ANNUAL MEETING: May 27, 2025",
        }], {"submission_type": "Annual Meeting", "period_covered": "2025-05-27"})

        self.assertEqual(result["status"], "Passed")


if __name__ == "__main__":
    unittest.main()
