import unittest

from gis_extraction_engine import extract_capital


class GisCapitalExtractionTests(unittest.TestCase):
    def test_extracts_core_capital_fields(self):
        items = extract_capital([{
            "page_number": 3,
            "page_type": "Capital Structure",
            "extracted_text": """
            CAPITAL STRUCTURE
            Authorized Capital Stock Total P1,000,000,000
            Subscribed Capital Stock Total P600,000,000
            Paid-Up Capital P550,000,000
            Filipino Ownership 60.5%
            Foreign Ownership 39.5%
            """,
            "image_quality_flag": "Passed",
        }])
        by_field = {item["field_name"]: item for item in items}

        self.assertEqual(by_field["authorized_capital"]["normalized_value"], "1000000000.0")
        self.assertEqual(by_field["subscribed_capital"]["normalized_value"], "600000000.0")
        self.assertEqual(by_field["paid_up_capital"]["normalized_value"], "550000000.0")
        self.assertEqual(by_field["filipino_ownership_percent"]["normalized_value"], "60.5")

    def test_ambiguous_value_is_not_normalized(self):
        items = extract_capital([{
            "page_number": 3,
            "page_type": "Capital Structure",
            "extracted_text": "Authorized Capital Stock Total P1,2,3",
            "image_quality_flag": "Passed",
        }])

        self.assertEqual(items, [])


if __name__ == "__main__":
    unittest.main()
