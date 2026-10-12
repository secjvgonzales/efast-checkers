import logging
import time
from datetime import date, datetime

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
from ui_helpers import page_header, format_timestamp_pst, section_heading, status_badge
from validation_engine import analyze_pages, detect_afs_reporting_years, validate_document

logger = logging.getLogger(__name__)

PROCESSING_STAGE_ORDER = (
    "prepare",
    "extract",
    "analyze",
    "validate",
    "structured",
    "persist",
    "review",
)

PROCESSING_STAGE_PROGRESS = {
    "prepare": 10,
    "extract": 32,
    "analyze": 52,
    "validate": 68,
    "structured": 84,
    "persist": 96,
    "review": 100,
}

PROCESSING_STAGE_DETAILS = {
    "prepare": ("Preparing PDF", "Saving the uploaded file and preparing its metadata for analysis."),
    "extract": ("Reading pages and extracting text / OCR", "Scanned pages may take longer because low-text pages can require OCR."),
    "analyze": ("Identifying document evidence", "Checking document type, company, reporting period, sections, orientation, and readability."),
    "validate": ("Running validations", "Preparing filing metadata, completeness, period, and document-quality results."),
    "structured": ("Extracting structured data", "Preparing report-specific figures, fields, and source evidence for reviewers."),
    "persist": ("Saving analysis results", "Saving page evidence, validations, and extracted data."),
    "review": ("Preparing reviewer view", "Finalizing the document for review and correction."),
}

AFS_PROCESSING_CHECKLIST = (
    ("prepare", "PDF received"),
    ("extract", "Text / OCR extraction"),
    ("analyze", "AFS identification and page analysis"),
    ("analyze", "Company information"),
    ("analyze", "Reporting period"),
    ("validate", "Required AFS components"),
    ("validate", "BIR filing evidence"),
    ("analyze", "Page orientation / readability"),
    ("structured", "Financial figure extraction"),
    ("validate", "Validation results"),
    ("persist", "Saving reviewer evidence"),
    ("review", "Preparing reviewer view"),
)

GIS_PROCESSING_CHECKLIST = (
    ("prepare", "PDF received"),
    ("extract", "Text / OCR extraction"),
    ("analyze", "GIS identification and page analysis"),
    ("analyze", "Company / SEC information"),
    ("analyze", "GIS reporting year"),
    ("structured", "Corporate profile"),
    ("structured", "Capital structure"),
    ("structured", "Directors / Officers"),
    ("structured", "Stockholders"),
    ("structured", "Certification / notarization"),
    ("validate", "Validation results"),
    ("persist", "Saving reviewer evidence"),
    ("review", "Preparing reviewer view"),
)


def _format_elapsed(seconds):
    total_seconds = max(0, int(seconds))
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


def _estimated_duration(file_size_bytes, ocr_used=False):
    size_mb = max(0, int(file_size_bytes or 0)) / (1024 * 1024)
    if size_mb < 5:
        low, high = 30, 90
    elif size_mb < 20:
        low, high = 60, 150
    else:
        low, high = 90, 300
    if ocr_used:
        low = max(low, 60)
        high = max(high, 180)
    return low, high


def _processing_snapshot(report_type, completed_stages=(), active_stage=None, failed_stage=None):
    completed = set(completed_stages)
    checklist = AFS_PROCESSING_CHECKLIST if report_type == "AFS" else GIS_PROCESSING_CHECKLIST
    rows = []
    for stage, label in checklist:
        if stage == failed_stage:
            state = "error"
        elif stage in completed:
            state = "completed"
        elif stage == active_stage:
            state = "active"
        else:
            state = "pending"
        rows.append({"stage": stage, "label": label, "state": state})
    progress = max((PROCESSING_STAGE_PROGRESS[stage] for stage in completed), default=0)
    return {"progress": progress, "rows": rows}


class ProcessingMonitor:
    def __init__(self, report_type, file_size_bytes):
        self.report_type = report_type
        self.file_size_bytes = file_size_bytes
        self.started = time.perf_counter()
        self.started_at = datetime.now().astimezone()
        self.completed_stages = []
        self.completion_times = {}
        self.active_stage = None
        self.ocr_used = False
        with st.container(border=True):
            self.title = st.empty()
            self.activity = st.status("Starting document analysis...", state="running", expanded=False)
            metric_cols = st.columns(3)
            self.started_metric = metric_cols[0].empty()
            self.elapsed = metric_cols[1].empty()
            self.estimate = metric_cols[2].empty()
            st.caption("Elapsed time updates at processing milestones.")
            self.progress = st.progress(0, text="0% complete")
            self.current = st.empty()
            st.caption(
                "Checklist states show processing progress only. They do not indicate whether a business validation passed."
            )
            self.checklist = st.empty()
            self.context = st.empty()
        self._render()

    def start(self, stage):
        self.active_stage = stage
        self._render()

    def complete(self, stage):
        if stage not in self.completed_stages:
            self.completed_stages.append(stage)
            self.completion_times[stage] = time.perf_counter() - self.started
        self.active_stage = None
        self._render()

    def set_ocr_used(self, ocr_used):
        self.ocr_used = bool(ocr_used)
        self._render()

    def fail(self):
        snapshot = _processing_snapshot(
            self.report_type,
            self.completed_stages,
            failed_stage=self.active_stage,
        )
        elapsed = time.perf_counter() - self.started
        last_completed = self.completed_stages[-1] if self.completed_stages else None
        last_label = PROCESSING_STAGE_DETAILS[last_completed][0] if last_completed else "None"
        failed_label = PROCESSING_STAGE_DETAILS[self.active_stage][0] if self.active_stage else "Unknown step"
        self.title.error("Analysis could not be completed")
        self.activity.update(label=f"Analysis stopped during: {failed_label}", state="error")
        self.started_metric.metric("Started at", self._started_at_display())
        self.elapsed.metric("Elapsed", _format_elapsed(elapsed))
        self.progress.progress(snapshot["progress"] / 100, text=f"{snapshot['progress']}% complete")
        self.current.error(f"Last completed stage: {last_label}\n\nFailed while: {failed_label}")
        self._render_checklist(snapshot)

    def finish(self, summary_rows):
        self.complete("review")
        elapsed = time.perf_counter() - self.started
        self.title.success("Analysis complete")
        self.activity.update(label="Document analysis completed", state="complete")
        self.started_metric.metric("Started at", self._started_at_display())
        self.elapsed.metric("Completed in", _format_elapsed(elapsed))
        self.estimate.metric("Processing status", "Reviewer results ready")
        self.current.success("Processing and persistence completed successfully.")
        self.checklist.markdown(
            "**COMPLETION SUMMARY**\n\n" + "\n".join(f"✓ {row}" for row in summary_rows)
        )
        self.context.empty()
        return elapsed

    def _render(self):
        snapshot = _processing_snapshot(
            self.report_type,
            self.completed_stages,
            active_stage=self.active_stage,
        )
        elapsed = time.perf_counter() - self.started
        low, high = _estimated_duration(self.file_size_bytes, self.ocr_used)
        self.title.markdown("### Analyzing document...")
        self.started_metric.metric("Started at", self._started_at_display())
        self.elapsed.metric("Elapsed", _format_elapsed(elapsed))
        self.estimate.metric("Estimated processing duration", f"{low}-{high} sec")
        self.progress.progress(snapshot["progress"] / 100, text=f"{snapshot['progress']}% complete")
        if self.active_stage:
            label, detail = PROCESSING_STAGE_DETAILS[self.active_stage]
            self.activity.update(
                label=f"{label} — the application is still processing",
                state="running",
            )
            self.current.markdown(
                f"""
                <div style="background:#EAF7EF;border:1px solid #B7E4CA;border-left:4px solid #0E5D3F;
                            border-radius:12px;padding:.85rem 1rem;">
                    <div style="color:#0E5D3F;font-size:.75rem;font-weight:800;letter-spacing:.1em;">CURRENTLY PROCESSING</div>
                    <div style="color:#0F172A;font-size:1.05rem;font-weight:800;margin-top:.3rem;">{label}</div>
                    <div style="color:#475569;font-size:.88rem;margin-top:.25rem;">{detail} The application is still processing.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            self.activity.update(label="Preparing the next processing step...", state="running")
            self.current.markdown("**Preparing the next processing step...**")
        self._render_checklist(snapshot)
        if self.ocr_used:
            self.context.warning("OCR was used for one or more low-text pages. Scanned documents can take longer.")
        else:
            self.context.info("Typical processing time is about 30-90 seconds. Large or scanned PDFs may take longer.")

    def _render_checklist(self, snapshot):
        symbols = {
            "completed": ("✓", "#0E5D3F"),
            "active": ("●", "#22C55E"),
            "pending": ("○", "#94A3B8"),
            "error": ("×", "#DC2626"),
        }
        rows = []
        for row in snapshot["rows"]:
            symbol, color = symbols[row["state"]]
            if row["state"] == "completed":
                timing = _format_elapsed(self.completion_times.get(row["stage"], 0))
            elif row["state"] == "active":
                timing = "processing"
            elif row["state"] == "error":
                timing = "error"
            else:
                timing = ""
            rows.append(
                f"<div style='display:flex;gap:.6rem;align-items:center;padding:.18rem 0;color:#334155;'>"
                f"<strong style='color:{color};width:1rem;'>{symbol}</strong>"
                f"<span>{row['label']}</span>"
                f"<span style='margin-left:auto;color:#64748B;font-size:.78rem;'>{timing}</span></div>"
            )
        self.checklist.markdown("**PROCESSING CHECKLIST**" + "".join(rows), unsafe_allow_html=True)

    def _started_at_display(self):
        return self.started_at.strftime("%I:%M:%S %p").lstrip("0")


def _mark_analysis_requested(state):
    if state.get("_intake_processing", False):
        return False
    state["_intake_processing"] = True
    state["_intake_run_requested"] = True
    return True


def _request_intake_analysis():
    _mark_analysis_requested(st.session_state)


def _set_post_analysis_navigation(state, document_id, page, context):
    state["active_document_id"] = document_id
    state["_current_page"] = page
    state["review_context"] = context


def render():
    context = st.session_state.get("review_context", DEFAULT_REPORT_TYPE)
    page_header(
        f"{context} REPORTS",
        "Upload / Intake",
        "Register filing metadata, upload a PDF, or load the explicit demonstration case.",
    )

    st.markdown(
        """
        <div class="metadata-strip">
            <div class="metadata-item"><div class="metadata-icon">1</div><div><span>Upload</span><strong>Add your AFS / GIS PDF</strong></div></div>
            <div class="metadata-item"><div class="metadata-icon">2</div><div><span>Metadata</span><strong>Enter filing details</strong></div></div>
            <div class="metadata-item"><div class="metadata-icon">3</div><div><span>Review</span><strong>Validate and proceed</strong></div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    main_col, side_col = st.columns([2.1, 1], gap="large")
    with main_col:
        with st.container(border=True):
            section_heading("Upload AFS / GIS PDF", "PDF files only. Real uploads are processed from extracted content.", "↥")
            uploaded = st.file_uploader("AFS / GIS PDF", type=["pdf"], label_visibility="collapsed")
            if uploaded:
                st.success(f"Selected file: {uploaded.name}")
            else:
                st.caption("Choose or drag one PDF into the upload area. Large or scanned files may require OCR and take longer.")

            st.divider()
            section_heading("Company and Filing Details", "Preserved metadata fields used by the existing processing workflow.", "▤")
            left, right = st.columns(2)
            with left:
                company_name = st.text_input("Company Name", DEFAULT_COMPANY)
                sec_no = st.text_input("SEC Registration Number", "")
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
            with right:
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

            processing = st.session_state.get("_intake_processing", False)
            action_label = "Processing..." if processing else "Validate & Continue"
            st.button(
                action_label,
                type="primary",
                disabled=processing,
                use_container_width=True,
                on_click=_request_intake_analysis,
            )

    with side_col:
        with st.container(border=True):
            section_heading("Submission Summary", "Live summary before analysis.", "✓")
            summary_rows = [
                ("File", uploaded.name if uploaded else "Not uploaded", bool(uploaded)),
                ("Company Name", company_name, bool(company_name)),
                ("Submission Type", submission_type, bool(submission_type)),
                ("SEC Registration No.", sec_no or "Not provided", bool(sec_no)),
                ("Filing Year", filing_year or "Not applicable", bool(filing_year) or report_type == "GIS"),
                ("Report Type", report_type, bool(report_type)),
                ("Period Covered Year", period_year, bool(period_year)),
            ]
            complete = sum(1 for _, _, ok in summary_rows if ok)
            for label, value, ok in summary_rows:
                st.markdown(f"{status_badge('Passed' if ok else 'Pending')} **{label}:** {value}", unsafe_allow_html=True)
        with st.container(border=True):
            section_heading("Metadata Completion", "Required demo intake readiness signal.", "◷")
            st.progress(complete / len(summary_rows))
            st.caption(f"{complete} of {len(summary_rows)} fields completed")
        with st.container(border=True):
            section_heading("Next Action", "Analyze when a PDF and required metadata are ready.", "↪")
            st.caption("Typical processing time: about 30-90 seconds. Large or scanned PDFs may take longer.")

    if st.session_state.get("_intake_run_requested", False):
        try:
            _run_intake_analysis(
                uploaded,
                company_name,
                sec_no,
                report_type,
                period_year,
                comparative_included,
                comparative_count,
                comparative_year_1,
                comparative_year_2,
                submission_type,
                filing_year,
                corporation_type,
                period_covered,
            )
        except Exception:
            logger.exception("Document analysis failed during the intake presentation flow")
            monitor = st.session_state.get("_active_processing_monitor")
            if monitor:
                monitor.fail()
            st.error("Unable to complete document analysis. Please retry or choose another PDF.")
            st.button("Try Again", key="retry_after_analysis_error", on_click=_request_intake_analysis)
        finally:
            st.session_state.pop("_active_processing_monitor", None)
            st.session_state["_intake_processing"] = False
            st.session_state["_intake_run_requested"] = False

    if st.button("Load Demo Document", type="primary"):
        document_id = ensure_demo_document(report_type)
        st.session_state["active_document_id"] = document_id
        st.success(f"{report_type} demo document #{document_id} loaded for Audentia Fortuna Holdings, Inc.")

    _render_test_uploads()
    st.info("Uploaded files are saved in the local uploads folder. Metadata and reviewer work are stored in SQLite.")


def _run_intake_analysis(
    uploaded,
    company_name,
    sec_no,
    report_type,
    period_year,
    comparative_included,
    comparative_count,
    comparative_year_1,
    comparative_year_2,
    submission_type,
    filing_year,
    corporation_type,
    period_covered,
):
    if not uploaded:
        st.error("Upload a PDF to analyze, or choose Load Demo Document for the explicit demo workflow.")
        return

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
        return

    monitor = ProcessingMonitor(report_type, getattr(uploaded, "size", 0))
    st.session_state["_active_processing_monitor"] = monitor

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
    monitor.start("prepare")
    document_id = insert_document(metadata)
    saved_path = prepare_uploaded_file(uploaded, UPLOADS_DIR)
    monitor.complete("prepare")

    monitor.start("extract")
    raw_pages, extraction_errors = extract_pdf_pages(saved_path)
    monitor.set_ocr_used(any(page.get("extraction_source") == "OCR Fallback" for page in raw_pages))
    monitor.complete("extract")
    if extraction_errors:
        with st.expander("Processing notes", expanded=False):
            for err in extraction_errors:
                st.warning(f"PDF parser issue: {err}")

    company_master = load_company_master()
    result_notices = []
    if raw_pages:
        monitor.start("analyze")
        pages = analyze_pages(raw_pages, metadata, company_master)
        monitor.complete("analyze")

        monitor.start("validate")
        validations = validate_document(pages, metadata, company_master)
        monitor.complete("validate")

        monitor.start("structured")
        gis_items = extract_gis_items(pages, metadata) if report_type == "GIS" else []
        detected_reporting_years = detect_afs_reporting_years(pages) if report_type == "AFS" else []
        figures = (
            []
            if report_type == "GIS"
            else extract_figures_from_pages(pages, detected_reporting_years or fiscal_year_candidates(metadata))
        )
        monitor.complete("structured")
        low_text = any(page.get("image_quality_flag") in ("Warning", "Failed") for page in pages)
        has_check_source = any(row.get("status") == "Check Source" for row in figures)
        if report_type == "GIS":
            analysis_outcome = "GIS Reviewer-Assistance Analysis Completed"
            outcome_message = (
                "GIS pages, content-based component evidence, meeting-period checks, "
                "and reviewer-assistance rules were completed."
            )
            result_notices.append(("success", f"**{analysis_outcome}** — {outcome_message}"))
            if low_text:
                result_notices.append(("warning",
                    "One or more GIS pages have low extracted text. Review the Text Layer/OCR source "
                    "and page quality signals in Document Review."
                ))
        elif low_text:
            analysis_outcome = "Possible Scanned / Low-Text PDF"
            outcome_message = (
                "Real PDF pages were analyzed, but one or more pages have low extracted text. "
                "This is a preliminary text-quality signal; image-content rotation not represented "
                "in PDF metadata is not automatically detected."
            )
            result_notices.append(("warning", f"**{analysis_outcome}** — {outcome_message}"))
        elif not figures or has_check_source:
            analysis_outcome = "Real PDF Analysis Completed — Figures Need Review"
            outcome_message = (
                "No supported financial figures were reliably extracted from this document."
                if not figures
                else "Ambiguous numeric formatting was detected in one or more figures; verify the original source."
            )
            result_notices.append(("warning", f"**{analysis_outcome}** — {outcome_message}"))
        else:
            analysis_outcome = "Real PDF Analysis Completed"
            outcome_message = "Real PDF pages, validations, and supported figure extraction were completed."
            result_notices.append(("success", f"**{analysis_outcome}** — {outcome_message}"))
        if report_type == "AFS" and not figures:
            result_notices.append(("warning", "No supported financial figures were reliably extracted from this document."))
        elif report_type == "AFS" and has_check_source:
            result_notices.append(("warning",
                "Some extracted values have ambiguous numeric formatting. Original raw values were retained; "
                "normalized peso values are blank until the reviewer verifies the source."
            ))
    else:
        pages = []
        figures = []
        gis_items = []
        analysis_outcome = "Extraction Failed — Manual Review Required"
        outcome_message = (
            "No page text could be extracted from the uploaded PDF. No demo pages or demo figures were inserted."
        )
        validations = []
        result_notices.append(("error", f"**{analysis_outcome}** — {outcome_message}"))

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
    monitor.start("persist")
    replace_document_analysis(document_id, pages, validations, figures)
    if report_type == "GIS":
        replace_gis_extracted_items(document_id, gis_items)
    monitor.complete("persist")

    monitor.start("review")
    st.session_state["active_document_id"] = document_id
    if raw_pages:
        summary_rows = [
            "PDF processed",
            f"{len(pages)} page{'s' if len(pages) != 1 else ''} analyzed",
            "Document sections and reporting period checked",
        ]
        if report_type == "AFS":
            summary_rows.append(f"{len(figures)} financial figure row{'s' if len(figures) != 1 else ''} extracted")
        else:
            summary_rows.append(f"{len(gis_items)} structured GIS item{'s' if len(gis_items) != 1 else ''} extracted")
        summary_rows.append("Reviewer results prepared")
        monitor.finish(summary_rows)
        st.toast("Document analysis completed. Reviewer results are ready.")
        for level, message in result_notices:
            getattr(st, level)(message)
    else:
        monitor.active_stage = "analyze"
        monitor.fail()
        for level, message in result_notices:
            getattr(st, level)(message)
        st.warning(f"Document #{document_id} was saved for manual review. Analysis was not marked as successfully completed.")
        st.button("Try Again", key=f"retry_after_failed_extraction_{document_id}", on_click=_request_intake_analysis)

    next_cols = st.columns(2 if report_type == "AFS" else 1)
    if next_cols[0].button("Open Document Review", key=f"open_review_after_upload_{document_id}", type="primary"):
        _set_post_analysis_navigation(
            st.session_state,
            document_id,
            "Document Review",
            report_type,
        )
        st.rerun()
    if report_type == "AFS" and next_cols[1].button("Open Figures Extraction Review", key=f"open_figures_after_upload_{document_id}"):
        _set_post_analysis_navigation(
            st.session_state,
            document_id,
            "AFS Figures Extraction Review",
            "AFS",
        )
        st.rerun()


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
    flash_message = st.session_state.pop("_test_upload_flash", None)
    if flash_message:
        st.success(flash_message)

    test_uploads = [document for document in get_documents() if not is_demo_document(document)]
    if not test_uploads:
        with st.container(border=True):
            section_heading("Test Uploads", "Temporary non-demo PDFs and safe cleanup controls.", "Files")
            st.info("No test uploads yet. Upload a PDF above to begin a temporary review.")
            st.caption("Seeded demo documents are protected and are not listed here.")
        return

    with st.expander(f"Test Uploads ({len(test_uploads)})", expanded=False):
        st.caption("Temporary non-demo PDFs are listed here for review and safe cleanup.")
        header = st.columns([2.25, 1.0, 1.0, 1.7, 1.45, 0.8])
        for column, label in zip(
            header,
            ["Company Name", "Type", "Period", "Analysis Status", "Uploaded At", "Action"],
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
                row[5].warning("Confirm")
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
