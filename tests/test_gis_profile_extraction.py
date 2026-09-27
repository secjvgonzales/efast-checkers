import unittest

from gis_extraction_engine import extract_profile, validate_profile_items


class GisProfileExtractionTests(unittest.TestCase):
    def test_extracts_profile_fields(self):
        pages = [{
            "page_number": 1,
            "page_type": "Corporate / Profile / Meeting Information",
            "extracted_text": """
            GENERAL INFORMATION SHEET FOR THE YEAR 2025
            Corporate Name: Haraya Demo Holdings, Inc.
            SEC Registration Number: CS123456789
            Fiscal Year End: December 31
            Actual Date of Annual Meeting: April 22, 2025
            Official Email Address: corporate@example.invalid
            """,
            "image_quality_flag": "Passed",
        }]

        items = extract_profile(pages)
        by_field = {item["field_name"]: item for item in items}

        self.assertEqual(by_field["company_name"]["value_text"], "Haraya Demo Holdings, Inc")
        self.assertEqual(by_field["sec_registration_no"]["normalized_value"], "CS123456789")
        self.assertEqual(by_field["gis_reporting_year"]["value_text"], "2025")
        self.assertIn("December", by_field["fiscal_year_end"]["value_text"])
        self.assertIn("April", by_field["actual_annual_meeting_date"]["value_text"])

    def test_profile_validation_detects_conflict(self):
        items = extract_profile([{
            "page_number": 1,
            "page_type": "Corporate / Profile / Meeting Information",
            "extracted_text": "GENERAL INFORMATION SHEET FOR THE YEAR 2025 Corporate Name: Other Demo Corp. SEC Registration Number: CS999",
            "image_quality_flag": "Passed",
        }])

        validations = validate_profile_items(items, {"company_name": "Expected Demo Corp.", "sec_registration_no": "CS123", "period_covered_year": 2025})

        self.assertIn("Failed", [row["status"] for row in validations])

    def test_sec_number_formats_and_missing_evidence_semantics(self):
        pages = [{
            "page_number": 1,
            "page_type": "Corporate / Profile / Meeting Information",
            "extracted_text": "GENERAL INFORMATION SHEET FOR THE YEAR 2025\nSEC FILE NO.: PW-102\nCorporate Name: Demo Corp.",
            "image_quality_flag": "Passed",
        }]
        items = extract_profile(pages)
        sec = next(item for item in items if item["field_name"] == "sec_registration_no")
        self.assertEqual(sec["normalized_value"], "PW102")
        validations = validate_profile_items(items, {"company_name": "Demo Corp.", "sec_registration_no": "PW 102", "period_covered_year": 2025})
        sec_validation = next(row for row in validations if row["rule_name"] == "GIS Extracted SEC Registration Number")
        self.assertEqual(sec_validation["status"], "Passed")

        missing = validate_profile_items([], {"company_name": "Demo Corp.", "sec_registration_no": "CS123", "period_covered_year": 2025})
        missing_sec = next(row for row in missing if row["rule_name"] == "GIS Extracted SEC Registration Number")
        self.assertEqual(missing_sec["status"], "Needs Review")

    def test_near_sec_ocr_variant_is_not_a_failed_conflict(self):
        items = extract_profile([{
            "page_number": 1,
            "page_type": "Corporate / Profile / Meeting Information",
            "extracted_text": "GENERAL INFORMATION SHEET FOR THE YEAR 2025\nSEC REGISTRATION NO.: 34171",
            "image_quality_flag": "Passed",
        }])
        validations = validate_profile_items(items, {"company_name": "", "sec_registration_no": "31171", "period_covered_year": 2025})
        sec_validation = next(row for row in validations if row["rule_name"] == "GIS Extracted SEC Registration Number")

        self.assertEqual(sec_validation["status"], "Needs Review")


if __name__ == "__main__":
    unittest.main()
