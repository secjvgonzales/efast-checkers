import unittest

from gis_extraction_engine import extract_stockholders


class GisStockholderTests(unittest.TestCase):
    def test_extracts_major_stockholder_row(self):
        items = extract_stockholders([{
            "page_number": 8,
            "page_type": "Stockholders' Information",
            "extracted_text": """
            STOCKHOLDERS' INFORMATION
            Demo Holdings Pte Ltd | Common | 12,500,000 | 62.5%
            Others | Common | 7,500,000 | 37.5%
            """,
            "image_quality_flag": "Passed",
        }])

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["metadata_json"]["share_count"], "12,500,000")
        self.assertEqual(items[0]["metadata_json"]["ownership_percent"], "62.5%")
        self.assertEqual(items[1]["metadata_json"]["stockholder_name"], "Others (Aggregate)")


if __name__ == "__main__":
    unittest.main()
