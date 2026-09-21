import html as html_lib

import pandas as pd
import streamlit as st

from db import save_reviewer_action, update_gis_bod_routing
from pdf_utils import quality_label
from storage import get_document, get_documents, get_pages, get_reviewer_actions, get_validations, load_revert_reasons
from ui_helpers import highlight_terms, render_status, reviewing_banner, show_document_selector, status_badge
from validation_engine import (
    evaluate_afs_completeness,
    evaluate_bir_filing,
    evaluate_gis_completeness,
    evaluate_gis_bod,
    final_recommendation,
    is_gis_submission,
    is_afs_submission,
    suggested_revert_reason,
)

# Pages that count as primary AFS source documents
_PRIMARY_PAGE_TYPES = {
    "Statement of Management's Responsibility",
    "Independent Auditor's Report",
    "Statement of Financial Position",
    "Balance Sheet",
    "Statement of Comprehensive Income",
    "Income Statement",
    "Statement of Operations",
    "Statement of Cash Flows",
    "Statement of Changes in Equity",
}


def _page_source_tag(page_type: str) -> str:
    if page_type in _PRIMARY_PAGE_TYPES:
        return "<span style='background:#d9f7e8;color:#0f6b43;border-radius:6px;font-size:.72rem;font-weight:700;padding:.15rem .45rem;margin-left:.5rem;'>Primary Source</span>"
    if "Notes" in page_type:
        return "<span style='background:#e8eef7;color:#1a3a6b;border-radius:6px;font-size:.72rem;font-weight:700;padding:.15rem .45rem;margin-left:.5rem;'>Supporting</span>"
    if page_type in ("Cover Page", "Other"):
        return "<span style='background:#f5f5f5;color:#666;border-radius:6px;font-size:.72rem;font-weight:700;padding:.15rem .45rem;margin-left:.5rem;'>Supporting</span>"
    return ""


def _render_validation_cards(validations):
    """Render validation results as styled cards instead of a plain dataframe."""
    status_styles = {
        "Passed": ("#d9f7e8", "#0f6b43", "#b7e8cb"),
        "Detected": ("#d9f7e8", "#0f6b43", "#b7e8cb"),
        "Warning": ("#fff7d9", "#856404", "#f5e9a0"),
        "Failed": ("#fde8e8", "#b91c1c", "#f5bebe"),
        "Needs Review": ("#e8eef7", "#1a3a6b", "#bfcee8"),
    }
    for v in validations:
        status = v.get("status") or "Needs Review"
        bg, fg, border = status_styles.get(status, ("#f5f5f5", "#333", "#ddd"))
        rule = html_lib.escape(str(v.get("rule_name") or ""))
        message = html_lib.escape(str(v.get("message") or ""))
        revert = html_lib.escape(str(v.get("suggested_revert_reason") or ""))
        revert_row = (
            f"<div style='margin-top:.3rem;font-size:.8rem;color:#587267;'>"
            f"<span style='font-weight:700;'>Suggested revert reason:</span> {revert}</div>"
            if revert else ""
        )
        st.markdown(
            f"""
            <div style="background:{bg};border:1px solid {border};border-left:4px solid {fg};
                        border-radius:10px;padding:.6rem .9rem;margin-bottom:.45rem;">
                <div style="display:flex;align-items:center;gap:.65rem;flex-wrap:wrap;">
                    <span style="background:{fg};color:#fff;border-radius:999px;font-size:.73rem;
                                 font-weight:700;padding:.18rem .52rem;">{status}</span>
                    <span style="font-weight:700;color:#103f2d;font-size:.9rem;">{rule}</span>
                </div>
                <div style="margin-top:.3rem;font-size:.85rem;color:#333;">{message}</div>
                {revert_row}
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_afs_completeness_check(pages, document):
    if not is_afs_submission(document):
        return

    completeness = evaluate_afs_completeness(pages, document)
    bir = evaluate_bir_filing(pages)
    st.subheader("AFS Completeness Check")
    if completeness["status"] == "Passed":
        st.success(completeness["message"])
    elif completeness["status"] == "Failed":
        st.error(completeness["message"])
    else:
        st.warning(completeness["message"])

    rows = [
        {
            "Component": item["component"],
            "Status": item["status"],
            "Detected Page(s)": item["detected_pages"],
        }
        for item in completeness["components"]
    ]
    rows.append({
        "Component": "Proof of BIR Filing",
        "Status": bir["status"],
        "Detected Page(s)": bir["detected_pages"],
    })
    status_styles = {
        "Detected": ("#d9f7e8", "#0f6b43"),
        "Missing": ("#fde8e8", "#b91c1c"),
        "Needs Review": ("#fff7d9", "#856404"),
    }
    table_rows = []
    for row in rows:
        bg, fg = status_styles.get(row["Status"], ("#f5f5f5", "#333"))
        table_rows.append(
            "<tr>"
            f"<td>{html_lib.escape(row['Component'])}</td>"
            f"<td><span style='background:{bg};color:{fg};border-radius:999px;padding:.18rem .55rem;font-weight:700;font-size:.78rem;'>{html_lib.escape(row['Status'])}</span></td>"
            f"<td>{html_lib.escape(row['Detected Page(s)'])}</td>"
            "</tr>"
        )
    st.markdown(
        "<table style='width:100%;border-collapse:collapse;margin:.35rem 0 .65rem;'>"
        "<thead><tr>"
        "<th style='text-align:left;padding:.45rem;border-bottom:1px solid #dfe9e3;'>Component</th>"
        "<th style='text-align:left;padding:.45rem;border-bottom:1px solid #dfe9e3;'>Status</th>"
        "<th style='text-align:left;padding:.45rem;border-bottom:1px solid #dfe9e3;'>Detected Page(s)</th>"
        "</tr></thead><tbody>"
        + "".join(table_rows)
        + "</tbody></table>",
        unsafe_allow_html=True,
    )
    st.caption(bir["note"])


def _render_gis_completeness_check(pages, document):
    completeness = evaluate_gis_completeness(pages, document.get("corporation_type") or "Stock")
    bod = evaluate_gis_bod(pages)
    st.subheader("GIS Completeness Check")
    if completeness["status"] == "Passed":
        st.success(completeness["message"])
    else:
        st.error(completeness["message"])

    rows = []
    for item in completeness["components"]:
        label = item["component"]
        if label == "Annex A / Primary Purpose":
            label += " (Optional)"
        elif label == "Beneficial Ownership Declaration":
            label += " (Conditional / Legacy)"
        elif not item.get("required"):
            label += " (Optional)"
        rows.append({
            "Component": label,
            "Status": item["status"],
            "Detected Page(s)": item["detected_pages"],
        })
    status_styles = {
        "Detected": ("#d9f7e8", "#0f6b43"),
        "Missing": ("#fde8e8", "#b91c1c"),
        "Needs Review": ("#fff7d9", "#856404"),
        "Not Present": ("#f5f5f5", "#666"),
        "Not Detected": ("#f5f5f5", "#666"),
        "Not Applicable / Accepted QA Copy": ("#e8eef7", "#1a3a6b"),
    }
    table_rows = []
    for row in rows:
        bg, fg = status_styles.get(row["Status"], ("#f5f5f5", "#333"))
        table_rows.append(
            "<tr>"
            f"<td>{html_lib.escape(row['Component'])}</td>"
            f"<td><span style='background:{bg};color:{fg};border-radius:999px;padding:.18rem .55rem;font-weight:700;font-size:.78rem;'>{html_lib.escape(row['Status'])}</span></td>"
            f"<td>{html_lib.escape(row['Detected Page(s)'])}</td>"
            "</tr>"
        )
    st.markdown(
        "<table style='width:100%;border-collapse:collapse;margin:.35rem 0 .65rem;'>"
        "<thead><tr>"
        "<th style='text-align:left;padding:.45rem;border-bottom:1px solid #dfe9e3;'>Component</th>"
        "<th style='text-align:left;padding:.45rem;border-bottom:1px solid #dfe9e3;'>Status</th>"
        "<th style='text-align:left;padding:.45rem;border-bottom:1px solid #dfe9e3;'>Detected Page(s)</th>"
        "</tr></thead><tbody>"
        + "".join(table_rows)
        + "</tbody></table>",
        unsafe_allow_html=True,
    )
    st.caption("BOD absence is excluded from GIS completeness; Annex A is optional.")

    st.subheader("Beneficial Ownership Routing")
    if bod["status"] == "Detected":
        st.info(f"{bod['message']} Select the page for reviewer-controlled routing representation.")
    else:
        st.caption(bod["message"])
    page_numbers = [page.get("page_number") for page in pages if page.get("page_number") is not None]
    options = [None] + page_numbers
    stored = document.get("gis_bod_routing_page")
    detected_default = bod["page_numbers"][0] if bod["page_numbers"] else None
    default = stored if stored in options else detected_default
    selected = st.selectbox(
        "BOD Page for Routing",
        options,
        index=options.index(default),
        format_func=lambda page: "None / Not Applicable" if page is None else f"Page {page}",
        key=f"gis_bod_routing_{document['id']}",
        disabled=not bool(page_numbers),
    )
    if st.button("Save BOD Routing Selection", key=f"save_gis_bod_routing_{document['id']}"):
        update_gis_bod_routing(document["id"], selected)
        st.success("BOD routing selection saved for reviewer reference only; no external routing was performed.")


def render():
    st.header("Document Review")
    context = st.session_state.get("review_context", "AFS")
    st.caption(
        f"{context} reviewer view for page classification, text evidence, period checks, "
        "suggested revert reasons, and final recommendation."
    )

    documents = [
        document for document in get_documents()
        if str(document.get("report_type") or "").upper() == context
    ]

    # Resolve active document — prefer session state, fall back to selector
    active_id = st.session_state.get("active_document_id")
    active_document = next(
        (document for document in documents if document["id"] == active_id),
        None,
    )
    if active_id and not active_document:
        active_id = None
        st.session_state["active_document_id"] = None
    if not active_id:
        active_id = show_document_selector(documents, f"doc_review_selector_{context.lower()}")
        if not active_id:
            return
        st.session_state["active_document_id"] = active_id
    else:
        with st.expander("Switch document", expanded=False):
            switched_id = show_document_selector(documents, f"doc_review_switcher_{context.lower()}")
            if switched_id and switched_id != active_id:
                if st.button("Load selected document", key=f"doc_review_switch_btn_{context.lower()}"):
                    st.session_state["active_document_id"] = switched_id
                    st.rerun()

    document_id = st.session_state["active_document_id"]
    document = get_document(document_id)

    if not document:
        st.warning("Selected document was not found. Please choose another from the selector below.")
        st.session_state.pop("active_document_id", None)
        return

    # ── Persistent "Currently Reviewing" banner ──────────────────────────────
    reviewing_banner(document)

    pages = get_pages(document_id)
    validations = get_validations(document_id)

    if is_gis_submission(document):
        _render_gis_completeness_check(pages, document)
    else:
        _render_afs_completeness_check(pages, document)

    # ── Validation Results ────────────────────────────────────────────────────
    st.subheader("GIS Validation Results" if is_gis_submission(document) else "Validation Results")
    if validations:
        _render_validation_cards(validations)
    else:
        st.info("No validation rows are available yet.")

    # ── Page Review ───────────────────────────────────────────────────────────
    st.subheader("Page Review")
    st.caption(
        "Page Layout uses PDF geometry. Rotation Metadata is read from the PDF when available. "
        "Image-content rotation that is not represented in PDF metadata is not automatically detected in this prototype."
    )
    if not pages:
        st.info("No page analysis data is available for this document.")
    for page in pages:
        page_type = page.get("page_type") or "Unknown"
        source_tag = _page_source_tag(page_type)
        title_html = f"Page {page['page_number']} — {page_type}{source_tag}"
        with st.expander(f"Page {page['page_number']} — {page_type}", expanded=page["page_number"] in [1, 3, 4]):
            # Source tag rendered inside expander for clarity
            if source_tag:
                st.markdown(source_tag, unsafe_allow_html=True)
            extraction_source = page.get("extraction_source") or "Text Layer"
            st.markdown(f"**Text Source:** {extraction_source}")
            if extraction_source == "OCR Fallback":
                st.caption("OCR fallback was used because little or no usable PDF text was detected.")
            cols = st.columns(5)
            cols[0].write("Page Layout")
            cols[0].markdown(f"**{page.get('orientation') or 'Unknown'}**")
            rotation = int(page.get("rotation_degrees") or 0)
            cols[1].write("Rotation Metadata")
            if rotation:
                cols[1].warning(f"{rotation}° · Review")
            else:
                cols[1].success("0°")
            cols[2].write("Company Match")
            cols[2].success("Matched") if page["detected_company_match"] else cols[2].warning("Review")
            cols[3].write("Period Match")
            cols[3].success("Matched") if page["detected_period_match"] else cols[3].warning("Review")
            cols[4].write("Quality Signal")
            text_length = page.get("text_length")
            if not text_length and page.get("text_preview"):
                text_length = len(str(page.get("text_preview") or "").strip())
            quality = quality_label(text_length, page.get("image_quality_flag"))
            if quality == "Readable":
                cols[4].success(quality)
            elif quality == "Low Text / Possible Scan":
                cols[4].warning(quality)
            else:
                cols[4].error(quality)
            cols[4].caption(f"{int(text_length or 0):,} chars")
            terms = [document["company_name"], str(document["period_covered_year"]), document["sec_registration_no"]]
            st.markdown(
                f"<div class='text-preview'>{highlight_terms(page['text_preview'], terms)}</div>",
                unsafe_allow_html=True,
            )

    # ── Reviewer Disposition ──────────────────────────────────────────────────
    st.divider()
    st.subheader("Reviewer Disposition")
    st.caption("Select a final recommendation, optionally note the suggested revert reason, and add reviewer remarks before saving.")

    recommendation = final_recommendation(validations)
    suggested = suggested_revert_reason(validations)
    reasons = load_revert_reasons()

    with st.form("reviewer_disposition"):
        col1, col2 = st.columns(2)
        with col1:
            final = st.selectbox(
                "Final Recommendation",
                ["Accept", "Revert", "Needs Review"],
                index=["Accept", "Revert", "Needs Review"].index(recommendation),
            )
        with col2:
            reason_options = [""] + reasons
            reason_index = reason_options.index(suggested) if suggested in reason_options else 0
            revert_reason = st.selectbox("Suggested Revert Reason", reason_options, index=reason_index)
        remarks = st.text_area(
            "Reviewer Remarks",
            placeholder="Add reviewer notes, issue details, or basis for override.",
            height=100,
        )
        saved = st.form_submit_button("Save Reviewer Recommendation", type="primary")
    if saved:
        save_reviewer_action(document_id, remarks, final, revert_reason)
        st.success("Reviewer recommendation saved.")

    # ── Reviewer Action History ───────────────────────────────────────────────
    st.subheader("Reviewer Action History")
    actions = get_reviewer_actions(document_id)
    if not actions:
        st.info("No reviewer actions have been saved for this document yet.")
    else:
        for action in actions:
            rec = action.get("final_recommendation") or "—"
            revert = action.get("final_revert_reason") or ""
            notes = action.get("reviewer_remarks") or ""
            ts = action.get("updated_at") or action.get("created_at") or "—"
            rec_colors = {
                "Accept": ("#d9f7e8", "#0f6b43"),
                "Revert": ("#fde8e8", "#b91c1c"),
                "Needs Review": ("#e8eef7", "#1a3a6b"),
            }
            bg, fg = rec_colors.get(rec, ("#f5f5f5", "#333"))
            revert_row = (
                f"<div style='margin-top:.3rem;color:#587267;font-size:.82rem;'>"
                f"<span style='font-weight:700;color:#103f2d;'>Revert reason:</span> {html_lib.escape(revert)}</div>"
                if revert else ""
            )
            notes_row = (
                f"<div style='margin-top:.25rem;color:#444;font-size:.84rem;font-style:italic;'>"
                f"&ldquo;{html_lib.escape(notes)}&rdquo;</div>"
                if notes else ""
            )
            st.markdown(
                f"""
                <div style="background:#fff;border:1px solid #dfe9e3;border-left:4px solid {fg};
                            border-radius:12px;padding:.7rem 1rem;margin-bottom:.5rem;">
                    <div style="display:flex;align-items:center;gap:.75rem;flex-wrap:wrap;">
                        <span style="background:{bg};color:{fg};border-radius:999px;font-size:.78rem;
                                     font-weight:700;padding:.2rem .6rem;">{html_lib.escape(rec)}</span>
                        <span style="color:#aaa;font-size:.78rem;">{html_lib.escape(str(ts))}</span>
                    </div>
                    {revert_row}
                    {notes_row}
                </div>
                """,
                unsafe_allow_html=True,
            )
