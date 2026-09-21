import unittest

from validation_engine import (
    classify_page,
    evaluate_afs_completeness,
    evaluate_bir_filing,
)


def page(number, text, page_type=None):
    return {
        "page_number": number,
        "page_type": page_type or classify_page(text),
        "extracted_text": text,
    }


def component(completeness, name):
    return next(item for item in completeness["components"] if item["component"] == name)


class AfsComponentDetectionTest(unittest.TestCase):
    def test_auditor_report_does_not_detect_management_responsibility(self):
        text = """
        Independent Auditor's Report
        Opinion
        We have audited the financial statements of Shell Pilipinas Corporation.
        Management is responsible for the preparation of the financial statements.
        """

        self.assertEqual(classify_page(text), "Independent Auditor's Report")
        completeness = evaluate_afs_completeness([page(1, text)])

        self.assertEqual(
            component(completeness, "Statement of Management's Responsibility")["status"],
            "Missing",
        )

    def test_explicit_management_responsibility_detected(self):
        text = """
        Statement of Management's Responsibility
        Management is responsible for the preparation and fair presentation of the
        financial statements in accordance with Philippine Financial Reporting Standards.
        """

        completeness = evaluate_afs_completeness([page(8, text)])

        self.assertEqual(
            component(completeness, "Statement of Management's Responsibility")["status"],
            "Detected",
        )

    def test_notarial_certificate_reference_does_not_detect_management_responsibility(self):
        text = """
        NOTARIAL CERTIFICATE
        Acknowledgement
        Subscribed and sworn to before me by the officers of the Company.
        This certificate refers to the Statement of Management's Responsibility
        attached to the annual financial statements.
        Notary Public
        Doc. No. 12; Page No. 4; Book No. 2; Series of 2025.
        """

        completeness = evaluate_afs_completeness([page(11, text)])

        self.assertNotEqual(
            component(completeness, "Statement of Management's Responsibility")["status"],
            "Detected",
        )

    def test_contents_page_does_not_detect_all_listed_components(self):
        text = """
        Contents
        Independent Auditor's Report
        Statement of Financial Position
        Statement of Income
        Statement of Comprehensive Income
        Statement of Changes in Equity
        Statement of Cash Flows
        Notes to Financial Statements
        """

        completeness = evaluate_afs_completeness([page(14, text)])
        primary_components = [
            "Statement of Financial Position / Balance Sheet",
            "Statement of Profit or Loss / Statement of Income",
            "Other Comprehensive Income",
            "Statement of Changes in Equity",
            "Statement of Cash Flows",
        ]

        for name in primary_components:
            self.assertNotEqual(component(completeness, name)["status"], "Detected")

    def test_financial_position_detected_from_heading_and_structure(self):
        text = """
        Statements of Financial Position
        As at December 31, 2025 and 2024
        Assets
        Current assets
        Total assets
        Liabilities
        Equity
        Total liabilities and equity
        """

        completeness = evaluate_afs_completeness([page(16, text)])

        self.assertEqual(
            component(completeness, "Statement of Financial Position / Balance Sheet")["status"],
            "Detected",
        )

    def test_financial_position_reference_without_structure_not_detected(self):
        text = """
        Notes to Financial Statements
        The carrying amounts are reconciled to the statement of financial position.
        This note should be read together with the related accounting policy.
        """

        completeness = evaluate_afs_completeness([page(49, text)])

        self.assertNotEqual(
            component(completeness, "Statement of Financial Position / Balance Sheet")["status"],
            "Detected",
        )

    def test_income_statement_detected_from_heading_and_structure(self):
        text = """
        Statements of Income
        For the years ended December 31, 2025 and 2024
        Sales and revenue
        Operating expenses
        Net income
        """

        completeness = evaluate_afs_completeness([page(17, text)])

        self.assertEqual(
            component(completeness, "Statement of Profit or Loss / Statement of Income")["status"],
            "Detected",
        )

    def test_income_reference_without_structure_not_detected(self):
        text = """
        Notes to Financial Statements
        Income taxes recognized in the statement of income and profit or loss
        are discussed below, including BIR filing positions and references.
        """

        completeness = evaluate_afs_completeness([page(32, text)])

        self.assertNotEqual(
            component(completeness, "Statement of Profit or Loss / Statement of Income")["status"],
            "Detected",
        )

    def test_comprehensive_income_detected_from_heading_and_structure(self):
        text = """
        Statements of Comprehensive Income
        Net income
        Other comprehensive income
        Total comprehensive income
        """

        completeness = evaluate_afs_completeness([page(18, text)])

        self.assertEqual(
            component(completeness, "Other Comprehensive Income")["status"],
            "Detected",
        )

    def test_comprehensive_income_page_does_not_also_detect_notes(self):
        text = """
        Statements of Comprehensive Income
        Net income
        Other comprehensive income
        Total comprehensive income
        See accompanying notes to financial statements.
        """

        completeness = evaluate_afs_completeness([page(18, text)])

        self.assertEqual(
            component(completeness, "Other Comprehensive Income")["status"],
            "Detected",
        )
        self.assertNotEqual(
            component(completeness, "Notes to Financial Statements")["status"],
            "Detected",
        )

    def test_true_notes_page_detected(self):
        text = """
        Notes to Financial Statements
        1. Corporate Information
        2. Summary of Significant Accounting Policies
        Basis of preparation
        """

        completeness = evaluate_afs_completeness([page(21, text)])

        self.assertEqual(
            component(completeness, "Notes to Financial Statements")["status"],
            "Detected",
        )

    def test_changes_in_equity_detected_from_heading_and_structure(self):
        text = """
        Statements of Changes in Equity
        Share capital
        Retained earnings
        Total equity
        """

        completeness = evaluate_afs_completeness([page(19, text)])

        self.assertEqual(
            component(completeness, "Statement of Changes in Equity")["status"],
            "Detected",
        )

    def test_cash_flows_detected_from_heading_and_structure(self):
        text = """
        Statements of Cash Flows
        Cash flows from operating activities
        Cash flows from investing activities
        Cash flows from financing activities
        """

        completeness = evaluate_afs_completeness([page(20, text)])

        self.assertEqual(
            component(completeness, "Statement of Cash Flows")["status"],
            "Detected",
        )

    def test_notes_references_do_not_detect_primary_statements(self):
        text = """
        Notes to Financial Statements
        The Company's total assets, net income, profit or loss, other comprehensive
        income, cash flows, and shareholders' equity are discussed in these notes.
        """

        completeness = evaluate_afs_completeness([page(21, text)])

        self.assertEqual(
            component(completeness, "Notes to Financial Statements")["status"],
            "Detected",
        )
        for name in [
            "Statement of Financial Position / Balance Sheet",
            "Statement of Profit or Loss / Statement of Income",
            "Other Comprehensive Income",
            "Statement of Changes in Equity",
            "Statement of Cash Flows",
        ]:
            self.assertNotEqual(component(completeness, name)["status"], "Detected")

    def test_bir_tax_references_are_not_proof_of_filing(self):
        text = """
        Income Tax
        The Company filed and submitted tax returns with the BIR and Bureau of Internal Revenue.
        The income tax return, filing positions, and reference to tax rules remain subject to examination.
        """

        result = evaluate_bir_filing([page(30, text)])

        self.assertEqual(result["status"], "Needs Review")

    def test_bir_filing_style_text_is_detected(self):
        text = """
        BIR received
        Received for filing
        Filed with the Bureau of Internal Revenue through eAFS submission.
        Transaction reference number: ABC-12345
        """

        self.assertEqual(evaluate_bir_filing([page(31, text)])["status"], "Detected")

    def test_demo_style_component_headings_still_satisfy_completeness(self):
        pages = [
            page(1, "Independent Auditor's Report\nWe have audited the financial statements."),
            page(2, "Statement of Management's Responsibility\nManagement is responsible."),
            page(3, "Statement of Financial Position\nAssets\nLiabilities\nEquity\nTotal assets"),
            page(4, "Statement of Income\nRevenue\nExpenses\nNet income"),
            page(5, "Statement of Comprehensive Income\nOther comprehensive income\nTotal comprehensive income"),
            page(6, "Statement of Changes in Equity\nShare capital\nRetained earnings\nTotal equity"),
            page(7, "Statement of Cash Flows\nOperating activities\nInvesting activities\nFinancing activities"),
            page(8, "Notes to Financial Statements\nSummary of significant accounting policies"),
        ]

        completeness = evaluate_afs_completeness(pages)

        self.assertEqual(completeness["status"], "Passed")


if __name__ == "__main__":
    unittest.main()
