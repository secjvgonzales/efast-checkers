from datetime import date

import streamlit as st

from config import DEFAULT_COMPANY, DEFAULT_FILING_YEAR, DEFAULT_PERIOD_YEAR, DEFAULT_REPORT_TYPE, DEFAULT_SUBMISSION_TYPE, UPLOADS_DIR
from db import insert_document, replace_document_analysis, replace_gis_extracted_items
from extraction_engine import extract_figures_from_pages, fiscal_year_candidates
from gis_extraction_engine import extract_gis_items
from pdf_utils import extract_pdf_pages, prepare_uploaded_file
from storage import (
    delete_test_document,
    document_analysis_summary,
    ensure_demo_document,
    get_documents,
    is_demo_document,
    load_company_master,
)
from ui_helpers import format_timestamp_pst
from validation_engine import analyze_pages, detect_afs_reporting_years, validate_document


def render():
    st.header("Upload / Intake")
    st.caption("Register AFS or GIS metadata, upload a PDF, or load the fictional demonstration case.")

    uploaded = st.file_uploader("AFS / GIS PDF", type=["pdf"])
    col1, col2 = st.columns(2)
    with col1:
        company_name = st.text_input("Company Name", DEFAULT_COMPANY)
        sec_no = st.text_input("SEC Registration Number", "")
        context = st.session_state.get("review_context", DEFAULT_REPORT_TYPE)
        if "intake_report_type" not in st.session_state:
            st.session_state["intake_report_type"] = context
        report_type = st.selectbox(
            "Report Type",
            ["AFS", "GIS"],
            key="intake_report_type",
        )
        if report_type == "AFS":
            period_year = st.number_input(
                "Period Covered Year",
                min_value=2000,
                max_value=2100,
                value=DEFAULT_PERIOD_YEAR,
                step=1,
            )
            corporation_type = ""
            period_covered = None
            comparative_included = st.radio(
                "Comparative Figures Included?",
                ["No", "Yes"],
                horizontal=True,
                help="Choose No for a current-period-only AFS.",
            )
        else:
            corporation_type = st.selectbox("Corporation Type", ["Stock", "Non-Stock"])
            period_year = st.number_input(
                "Period Year",
                min_value=2000,
                max_value=2100,
                value=DEFAULT_PERIOD_YEAR,
                step=1,
            )
            period_covered = st.date_input(
                "Period Covered",
                value=date(int(period_year), 12, 31),
                key="gis_period_covered",
            )
            comparative_included = "No"
    with col2:
        if report_type == "AFS":
            submission_type = st.text_input("Submission Type", DEFAULT_SUBMISSION_TYPE)
            filing_year = st.number_input(
                "Filing Year",
                min_value=2000,
                max_value=2100,
                value=DEFAULT_FILING_YEAR,
                step=1,
            )
        else:
            submission_type = st.selectbox(
                "Submission Type",
                [
                    "Annual Meeting",
                    "Special Meeting",
                    "Amendment / Amended GIS",
                    "No Meeting / Non-Holding of Annual Meeting",
                ],
            )
            filing_year = None
        comparative_count = 0
        comparative_year_1 = None
        comparative_year_2 = None
        if comparative_included == "Yes":
            comparative_count = st.selectbox(
                "Number of Comparative Years",
                [1, 2],
                format_func=lambda count: str(count),
            )
            comparative_year_1 = st.number_input(
                "Comparative Year 1",
                min_value=2000,
                max_value=2100,
                value=max(2000, int(period_year) - 1),
                step=1,
            )
            if comparative_count == 2:
                comparative_year_2 = st.number_input(
                    "Comparative Year 2",
                    min_value=2000,
                    max_value=2100,
                    value=max(2000, int(period_year) - 2),
                    step=1,
                )
    submitted = st.button("Save Intake and Analyze", type="primary")

    if submitted:
        if not uploaded:
            st.error("Upload a PDF to analyze, or choose Load Demo Document for the explicit demo workflow.")
        else:
            selected_comparative_years = (
                [int(comparative_year_1)]
                if comparative_included == "Yes" and comparative_count == 1
                else [int(comparative_year_1), int(comparative_year_2)]
                if comparative_included == "Yes"
                else []
            )
            year_errors = _validate_reporting_years(int(period_year), selected_comparative_years)
            if year_errors:
                for error in year_errors:
                    st.error(error)
            else:
                metadata = {
                    "filename": uploaded.name,
                    "company_name": company_name,
                    "sec_registration_no": sec_no,
                    "report_type": report_type,
                    "period_covered_year": int(period_year),
                    "comparative_years": ", ".join(str(year) for year in selected_comparative_years),
                    "submission_type": submission_type,
                    "filing_year": int(filing_year) if filing_year else None,
                    "corporation_type": corporation_type,
                    "period_covered": period_covered.isoformat() if period_covered else None,
                }
                document_id = insert_document(metadata)
                saved_path = prepare_uploaded_file(uploaded, UPLOADS_DIR)
                with st.spinner("Reading PDF text; using OCR only for low-text pages when available..."):
                    raw_pages, extraction_errors = extract_pdf_pages(saved_path)
                if extraction_errors:
                    for err in extraction_errors:
                        st.warning(f"PDF parser issue: {err}")
                company_master = load_company_master()
                if raw_pages:
                    pages = analyze_pages(raw_pages, metadata, company_master)
                    gis_items = extract_gis_items(pages, metadata) if report_type == "GIS" else []
                    validations = validate_document(pages, metadata, company_master)
                    detected_reporting_years = detect_afs_reporting_years(pages) if report_type == "AFS" else []
                    figures = (
                        []
                        if report_type == "GIS"
                        else extract_figures_from_pages(pages, detected_reporting_years or fiscal_year_candidates(metadata))
                    )
                    low_text = any(page.get("image_quality_flag") in ("Warning", "Failed") for page in pages)
                    has_check_source = any(row.get("status") == "Check Source" for row in figures)
                    if report_type == "GIS":
                        analysis_outcome = "GIS Reviewer-Assistance Analysis Completed"
                        outcome_message = (
                            "GIS pages, content-based component evidence, meeting-period checks, "
                            "and reviewer-assistance rules were completed."
                        )
                        st.success(f"**{analysis_outcome}** — {outcome_message}")
                        if low_text:
                            st.warning(
                                "One or more GIS pages have low extracted text. Review the Text Layer/OCR source "
                                "and page quality signals in Document Review."
                            )
                    elif low_text:
                        analysis_outcome = "Possible Scanned / Low-Text PDF"
                        outcome_message = (
                            "Real PDF pages were analyzed, but one or more pages have low extracted text. "
                            "This is a preliminary text-quality signal; image-content rotation not represented "
                            "in PDF metadata is not automatically detected."
                        )
                        st.warning(f"**{analysis_outcome}** — {outcome_message}")
                    elif not figures or has_check_source:
                        analysis_outcome = "Real PDF Analysis Completed — Figures Need Review"
                        outcome_message = (
                            "No supported financial figures were reliably extracted from this document."
                            if not figures
                            else "Ambiguous numeric formatting was detected in one or more figures; verify the original source."
                        )
                        st.warning(f"**{analysis_outcome}** — {outcome_message}")
                    else:
                        analysis_outcome = "Real PDF Analysis Completed"
                        outcome_message = "Real PDF pages, validations, and supported figure extraction were completed."
                        st.success(f"**{analysis_outcome}** — {outcome_message}")
                    if report_type == "AFS" and not figures:
                        st.warning("No supported financial figures were reliably extracted from this document.")
                    elif report_type == "AFS" and has_check_source:
                        st.warning(
                            "Some extracted values have ambiguous numeric formatting. Original raw values were retained; "
                            "normalized peso values are blank until the reviewer verifies the source."
                        )
                else:
                    pages = []
                    figures = []
                    gis_items = []
                    analysis_outcome = "Extraction Failed — Manual Review Required"
                    outcome_message = (
                        "No page text could be extracted from the uploaded PDF. No demo pages or demo figures were inserted."
                    )
                    validations = []
                    st.error(f"**{analysis_outcome}** — {outcome_message}")

                validations.append({
                    "rule_name": "PDF analysis outcome",
                    "status": "Passed" if analysis_outcome in (
                        "Real PDF Analysis Completed",
                        "GIS Reviewer-Assistance Analysis Completed",
                    ) else "Needs Review",
                    "message": f"{analysis_outcome}. {outcome_message}",
                    "suggested_revert_reason": (
                        "Poor image quality"
                        if analysis_outcome in ("Possible Scanned / Low-Text PDF", "Extraction Failed — Manual Review Required")
                        else ""
                    ),
                })
                replace_document_analysis(document_id, pages, validations, figures)
                if report_type == "GIS":
                    replace_gis_extracted_items(document_id, gis_items)
                st.session_state["active_document_id"] = document_id
                st.success(f"Document #{document_id} saved and analyzed.")

    if st.button("Load Demo Document", type="primary"):
        document_id = ensure_demo_document(report_type)
        st.session_state["active_document_id"] = document_id
        st.success(f"{report_type} demo document #{document_id} loaded for Audentia Fortuna Holdings, Inc.")

    _render_test_uploads()
    st.info("Uploaded files are saved in the local uploads folder. Metadata and reviewer work are stored in SQLite.")


def _validate_reporting_years(period_year, comparative_years):
    errors = []
    if len(comparative_years) > 2:
        errors.append("A maximum of 2 comparative years is supported.")
    if len(set(comparative_years)) != len(comparative_years):
        errors.append("Comparative years must not be duplicates.")
    if any(year == period_year for year in comparative_years):
        errors.append("A comparative year cannot equal the Period Covered Year.")
    if any(year > period_year for year in comparative_years):
        errors.append("Each comparative year must be earlier than the Period Covered Year.")
    return errors


def _render_test_uploads():
    st.subheader("Test Uploads")
    st.caption("Temporary non-demo PDFs are listed here for review and safe cleanup.")

    flash_message = st.session_state.pop("_test_upload_flash", None)
    if flash_message:
        st.success(flash_message)

    test_uploads = [document for document in get_documents() if not is_demo_document(document)]
    if not test_uploads:
        st.info("No test uploads yet. Upload a PDF above to begin a temporary review.")
        st.caption("Seeded demo documents are protected and are not listed here.")
        return

    header = st.columns([2.25, 1.0, 1.0, 1.7, 1.45, 0.8])
    for column, label in zip(
        header,
        ["Company Name", "Report Type", "Period Covered", "Analysis Status / Recommendation", "Uploaded At", "Action"],
    ):
        column.markdown(f"**{label}**")

    pending_id = st.session_state.get("_pending_test_upload_delete_id")
    for document in test_uploads:
        document_id = document["id"]
        row = st.columns([2.25, 1.0, 1.0, 1.7, 1.45, 0.8])
        row[0].write(document.get("company_name") or "—")
        row[1].write(document.get("report_type") or "—")
        row[2].write(document.get("period_covered_year") or "—")
        row[3].write(document_analysis_summary(document_id))
        row[4].write(format_timestamp_pst(document.get("uploaded_at") or ""))
        if pending_id == document_id:
            row[5].warning("Confirm below")
            st.warning("Delete this test upload and its analysis data?")
            confirm_col, cancel_col = st.columns([1, 1])
            if confirm_col.button("Confirm Delete", key=f"confirm_delete_test_upload_{document_id}", type="primary"):
                result = delete_test_document(document_id)
                if result["deleted"]:
                    if st.session_state.get("active_document_id") == document_id:
                        st.session_state["active_document_id"] = None
                    st.session_state.pop("_pending_test_upload_delete_id", None)
                    message = f"Test upload #{document_id} and its analysis data were deleted."
                    if result.get("file_cleanup_warning"):
                        message = f"{message} {result['file_cleanup_warning']}"
                    st.session_state["_test_upload_flash"] = message
                    st.rerun()
                st.error(result["reason"])
            if cancel_col.button("Cancel", key=f"cancel_delete_test_upload_{document_id}"):
                st.session_state.pop("_pending_test_upload_delete_id", None)
                st.rerun()
        elif row[5].button("Delete", key=f"delete_test_upload_{document_id}"):
            st.session_state["_pending_test_upload_delete_id"] = document_id
            st.rerun()

    st.caption("Seeded demo documents remain protected and cannot be deleted from this interface.")
