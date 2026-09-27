import unittest

from validation_engine import analyze_pages, classify_gis_page, evaluate_gis_completeness, validate_gis_document


class GisClassificationTests(unittest.TestCase):
    def test_identifies_core_gis_sections(self):
        self.assertEqual(
            classify_gis_page("AMENDED GENERAL INFORMATION SHEET FOR THE YEAR 2025 Corporate Name: Demo Corp. SEC Registration Number: CS123 Fiscal Year End: December 31."),
            "Corporate / Profile / Meeting Information",
        )
        self.assertEqual(classify_gis_page("CAPITAL STRUCTURE Authorized Capital Stock Subscribed Capital Paid-Up Capital"), "Capital Structure")
        self.assertEqual(classify_gis_page("DIRECTORS AND OFFICERS Name Nationality Board Position Gender Officer Position"), "Directors / Officers")
        self.assertEqual(classify_gis_page("STOCKHOLDERS' INFORMATION Name Shares Subscribed % Ownership Amount Paid"), "Stockholders' Information")

    def test_repeated_headers_are_not_section_evidence(self):
        text = "AMENDED GENERAL INFORMATION SHEET STOCK CORPORATION PLEASE PRINT LEGIBLY CORPORATE NAME"
        self.assertEqual(classify_gis_page(text), "Other / Unclassified")

    def test_other_and_certification_require_structural_anchors(self):
        self.assertEqual(
            classify_gis_page("Investment of Corporate Funds Treasury Shares Retained Earnings Dividends Declared"),
            "Investments / Other Corporate Information",
        )

    def test_partial_capital_table_anchors_are_recognized(self):
        self.assertEqual(
            classify_gis_page("NUMBER OF SHARES PAR/STATED VALUE AMOUNT Type of Shares"),
            "Capital Structure",
        )
        self.assertEqual(
            classify_gis_page("Corporate Secretary certifies the filing. Subscribed and Sworn before a Notary Public. Doc. No. 1."),
            "Corporate Secretary Attestation / Notarization",
        )

    def test_continuation_pages_inherit_only_compatible_rosters(self):
        pages = analyze_pages([
            {"page_number": 4, "text": "DIRECTORS AND OFFICERS Name Nationality Board Position Gender Officer Position Stockholder"},
            {"page_number": 5, "text": "Name Nationality Board Position Gender Officer Position Stockholder"},
            {"page_number": 6, "text": "STOCKHOLDERS' INFORMATION Name Shares Subscribed % Ownership Amount Paid"},
            {"page_number": 7, "text": "Name Shares Subscribed % Ownership Amount Paid"},
        ], {"report_type": "GIS", "period_covered_year": 2025}, {})

        self.assertEqual([page["page_type"] for page in pages], [
            "Directors / Officers", "Directors / Officers", "Stockholders' Information", "Stockholders' Information",
        ])

    def test_amla_absence_does_not_fail_stock_completeness(self):
        pages = [
            {"page_number": 1, "page_type": "Corporate / Profile / Meeting Information", "extracted_text": "General Information Sheet"},
            {"page_number": 2, "page_type": "Capital Structure", "extracted_text": "Authorized Capital Stock"},
            {"page_number": 3, "page_type": "Directors / Officers", "extracted_text": "Directors and Officers"},
            {"page_number": 4, "page_type": "Stockholders' Information", "extracted_text": "Stockholders Information"},
            {"page_number": 5, "page_type": "Investments / Other Corporate Information", "extracted_text": "Investments retained earnings dividends"},
            {"page_number": 6, "page_type": "Corporate Secretary Attestation / Notarization", "extracted_text": "Corporate Secretary Subscribed and sworn Notary Public"},
        ]

        result = evaluate_gis_completeness(pages, "Stock")

        self.assertEqual(result["status"], "Passed")
        amla = next(item for item in result["components"] if item["component"] == "AMLA Information")
        self.assertFalse(amla["required"])

    def test_low_text_missing_section_is_needs_review_not_missing(self):
        pages = [{
            "page_number": 1,
            "page_type": "Corporate / Profile / Meeting Information",
            "extracted_text": "General Information Sheet Corporate Name SEC Registration Number Fiscal Year End",
            "image_quality_flag": "Failed",
        }]
        result = evaluate_gis_completeness(pages, "Stock")

        self.assertEqual(result["status"], "Needs Review")
        self.assertTrue(all(item["status"] in ("Detected", "Needs Review") for item in result["components"] if item["required"]))

    def test_weak_ocr_missing_critical_fields_needs_review(self):
        validations = validate_gis_document([{
            "page_number": 1,
            "page_type": "Corporate / Profile / Meeting Information",
            "extracted_text": "GENERAL INFORMATION SHEET Corporate Name",
            "image_quality_flag": "Warning",
            "extraction_source": "OCR Fallback",
        }], {"report_type": "GIS", "company_name": "Demo Corp.", "sec_registration_no": "CS123", "period_covered_year": 2025, "submission_type": "Annual Meeting"})
        image_quality = next(row for row in validations if row["rule_name"] == "GIS Image Quality")

        self.assertEqual(image_quality["status"], "Needs Review")


if __name__ == "__main__":
    unittest.main()
