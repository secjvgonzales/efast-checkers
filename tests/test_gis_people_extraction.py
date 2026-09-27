import unittest

from gis_extraction_engine import extract_people


class GisPeopleExtractionTests(unittest.TestCase):
    def test_extracts_director_officer_without_tin(self):
        items = extract_people([{
            "page_number": 5,
            "page_type": "Directors / Officers",
            "extracted_text": """
            DIRECTORS AND OFFICERS
            Maria Santos | Filipino | Director | President | Female | Stockholder | TIN 123-456-789
            Juan Reyes | Filipino | Independent Director | Treasurer | Male | Stockholder
            """,
            "image_quality_flag": "Passed",
        }])

        self.assertEqual(len(items), 2)
        self.assertNotIn("123-456-789", str(items))
        self.assertIn("Director", items[0]["metadata_json"]["board_role_or_indicator"])

    def test_partial_row_needs_review(self):
        items = extract_people([{
            "page_number": 6,
            "page_type": "Directors / Officers",
            "extracted_text": "Continuation Page\nElena Cruz | Female",
            "image_quality_flag": "Passed",
        }])

        self.assertEqual(items[0]["review_status"], "Needs Review")


if __name__ == "__main__":
    unittest.main()
