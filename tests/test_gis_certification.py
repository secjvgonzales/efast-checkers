import unittest

from gis_extraction_engine import extract_certification


class GisCertificationTests(unittest.TestCase):
    def test_extracts_certification_and_notarization_evidence(self):
        items = extract_certification([{
            "page_number": 15,
            "page_type": "Corporate Secretary Attestation / Notarization",
            "extracted_text": """
            I certify that the foregoing information is true and correct.
            Ana Demo Corporate Secretary
            SUBSCRIBED AND SWORN before me, a Notary Public.
            Doc. No. 1; Page No. 2; Book No. III; Series of 2025.
            """,
            "image_quality_flag": "Passed",
        }])
        fields = {item["field_name"] for item in items}

        self.assertIn("attestation_present", fields)
        self.assertIn("notarization_present", fields)
        self.assertIn("corporate_secretary_name", fields)


if __name__ == "__main__":
    unittest.main()
