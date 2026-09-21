import unittest

from validation_engine import validate_company_master


class CompanyMasterValidationTests(unittest.TestCase):
    def test_missing_master_returns_needs_review(self):
        result = validate_company_master(
            "Del Monte Philippines, Inc. PW00000112",
            {"company_name": "Del Monte Philippines, Inc.", "sec_registration_no": "PW00000112"},
            {"company_name": "Audentia Fortuna Holdings, Inc.", "sec_registration_no": "CS202102938"},
        )
        self.assertEqual(result["status"], "Needs Review")

    def test_relevant_master_conflict_fails(self):
        result = validate_company_master(
            "Different Company CS202102938",
            {"company_name": "Audentia Fortuna Holdings, Inc.", "sec_registration_no": "CS202102938"},
            {"company_name": "Audentia Fortuna Holdings, Inc.", "sec_registration_no": "CS202102938"},
        )
        self.assertEqual(result["status"], "Failed")
        self.assertEqual(result["suggested_revert_reason"], "Wrong company profile")


if __name__ == "__main__":
    unittest.main()
