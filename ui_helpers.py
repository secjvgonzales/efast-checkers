import html
from datetime import datetime
from typing import Dict, Iterable, List, Optional

import pandas as pd
import streamlit as st


STATUS_TONES = {
    "Passed": ("#D9F2E6", "#0E5D3F"),
    "Accepted": ("#D9F2E6", "#0E5D3F"),
    "Accept": ("#D9F2E6", "#0E5D3F"),
    "Reviewed": ("#D9F2E6", "#0E5D3F"),
    "Corrected": ("#D9F2E6", "#0E5D3F"),
    "Detected": ("#D9F2E6", "#0E5D3F"),
    "Present": ("#D9F2E6", "#0E5D3F"),
    "Ready for Quick Validation": ("#D9F2E6", "#0E5D3F"),
    "Warning": ("#FFF7D6", "#92400E"),
    "Needs Review": ("#FFF7D6", "#92400E"),
    "Check Source": ("#FFF7D6", "#92400E"),
    "Conditional": ("#FFF7D6", "#92400E"),
    "Failed": ("#FEE2E2", "#B91C1C"),
    "Revert": ("#FEE2E2", "#B91C1C"),
    "Reverted": ("#FEE2E2", "#B91C1C"),
    "Rejected": ("#FEE2E2", "#B91C1C"),
    "Missing": ("#FEE2E2", "#B91C1C"),
    "Not Detected": ("#E8EEF7", "#1E3A8A"),
    "Not Present": ("#E8EEF7", "#1E3A8A"),
    "Pending": ("#E8EEF7", "#1E3A8A"),
}


def status_badge(status: str) -> str:
    status = status or "Needs Review"
    bg, fg = STATUS_TONES.get(status, ("#F1F5F9", "#334155"))
    safe = html.escape(str(status))
    return f"<span class='badge' style='background:{bg};color:{fg}'>{safe}</span>"


def recommendation_badge(rec: str) -> str:
    return status_badge(rec or "Needs Review")


def metric_card(label: str, value, caption: str = "", icon: str = "", tone: str = "green") -> None:
    safe_label = html.escape(str(label))
    safe_value = html.escape(str(value))
    safe_caption = html.escape(str(caption or ""))
    safe_icon = html.escape(str(icon or ""))
    st.markdown(
        f"""
        <div class="metric-card metric-card--{tone}">
            <div class="metric-card-top">
                <div class="metric-label">{safe_label}</div>
                <div class="metric-icon">{safe_icon}</div>
            </div>
            <div class="metric-value">{safe_value}</div>
            <div class="metric-caption">{safe_caption}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def page_header(section: str, title: str, subtitle: str = "", badge: str = "") -> None:
    safe_section = html.escape(str(section or ""))
    safe_title = html.escape(str(title or ""))
    safe_subtitle = html.escape(str(subtitle or ""))
    badge_html = f"<span class='page-badge'>{html.escape(str(badge))}</span>" if badge else ""
    st.markdown(
        f"""
        <div class="page-header">
            <div class="eyebrow">{safe_section}</div>
            <div class="page-title-row"><h1>{safe_title}</h1>{badge_html}</div>
            <p>{safe_subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_heading(title: str, subtitle: str = "", icon: str = "") -> None:
    st.markdown(
        f"""
        <div class="section-heading">
            <div class="section-icon">{html.escape(str(icon or ''))}</div>
            <div>
                <h3>{html.escape(str(title))}</h3>
                <p>{html.escape(str(subtitle or ''))}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def info_card(title: str, body: str, tone: str = "mint", icon: str = "") -> None:
    st.markdown(
        f"""
        <div class="info-card info-card--{tone}">
            <div class="info-card-icon">{html.escape(str(icon or ''))}</div>
            <div><strong>{html.escape(str(title))}</strong><br><span>{html.escape(str(body))}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def empty_state(title: str, body: str) -> None:
    st.markdown(
        f"""
        <div class="empty-state">
            <strong>{html.escape(str(title))}</strong>
            <p>{html.escape(str(body))}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metadata_strip(fields: Iterable) -> None:
    items = []
    for label, value, icon in fields:
        items.append(
            "<div class='metadata-item'>"
            f"<div class='metadata-icon'>{html.escape(str(icon or ''))}</div>"
            "<div>"
            f"<span>{html.escape(str(label))}</span>"
            f"<strong>{html.escape(str(value if value not in (None, '') else '—'))}</strong>"
            "</div></div>"
        )
    st.markdown(f"<div class='metadata-strip'>{''.join(items)}</div>", unsafe_allow_html=True)


def validation_card(title: str, status: str, message: str = "", detail: str = "") -> None:
    bg, fg = STATUS_TONES.get(status or "Needs Review", ("#F1F5F9", "#334155"))
    detail_html = f"<small>{html.escape(str(detail))}</small>" if detail else ""
    st.markdown(
        f"""
        <div class="validation-card" style="border-left-color:{fg};">
            <div>{status_badge(status)} <strong>{html.escape(str(title))}</strong></div>
            <p>{html.escape(str(message or ''))}</p>
            {detail_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def timeline_item(title: str, subtitle: str = "", status: str = "") -> None:
    bg, fg = STATUS_TONES.get(status or "Passed", ("#D9F2E6", "#0E5D3F"))
    st.markdown(
        f"""
        <div class="timeline-item">
            <div class="timeline-dot" style="background:{fg};"></div>
            <div><strong>{html.escape(str(title))}</strong><br><span>{html.escape(str(subtitle or ''))}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def format_peso(value) -> str:
    try:
        v = float(value)
        if v != v:  # NaN check
            return "₱—"
        return f"₱{v:,.2f}"
    except (TypeError, ValueError):
        return "₱—"


def format_timestamp_pst(ts: str) -> str:
    """Format an ISO datetime string as '16 Jul 2026, 9:59 AM PST'."""
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(str(ts)[:19])
        return dt.strftime("%-d %b %Y, %-I:%M %p PST")
    except (ValueError, TypeError):
        return str(ts)[:16] if ts else "—"


def highlight_terms(text: str, terms: List[str]) -> str:
    safe = html.escape(str(text or ""))
    for term in terms:
        if not term:
            continue
        escaped_term = html.escape(term)
        safe = safe.replace(escaped_term, f"<mark>{escaped_term}</mark>")
    return safe


def render_status(flag: str) -> None:
    flag = (flag or "").lower()
    if flag in ("ok", "good"):
        st.success("Good")
    elif flag in ("low", "poor", "bad"):
        st.error("Low Quality")
    else:
        st.warning(flag or "Unknown")


def dataframe_download(df: pd.DataFrame, filename: str, label: str = "Download CSV") -> None:
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(label, data=csv, file_name=filename, mime="text/csv")


def show_document_selector(documents: List[Dict], key: str) -> Optional[int]:
    if not documents:
        st.info("No documents found. Load the demo document or upload a PDF from the Upload / Intake page.")
        return None
    id_by_label = {
        f"#{doc['id']} — {doc['company_name']} — {doc['period_covered_year']}": doc["id"]
        for doc in documents
    }
    labels = list(id_by_label.keys())
    selected = st.selectbox("Document", labels, key=key)
    return id_by_label[selected]


def clean_source_snippet(snippet: str, context: str = "", anchor: str = "", max_chars: int = 140) -> str:
    """Clean a source excerpt for display without changing stored source text."""
    source = str(context or snippet or "")
    source = " ".join(source.split())
    if not source:
        return ""
    anchor_index = -1
    if anchor:
        anchor_index = source.lower().find(str(anchor).lower())
    if len(source) <= max_chars:
        return source
    start = max(0, anchor_index - 58) if anchor_index >= 0 else 0
    if start > 0:
        while start < len(source) and not source[start - 1].isspace():
            start += 1
    elif source[0].islower():
        first_space = source.find(" ")
        start = first_space + 1 if first_space >= 0 else 0
    end = min(len(source), start + max_chars)
    if end < len(source):
        word_end = source.rfind(" ", start, end)
        if word_end > start:
            end = word_end
    excerpt = source[start:end].strip()
    if start > 0:
        excerpt = "…" + excerpt
    if end < len(source):
        excerpt = excerpt.rstrip(" .,:;") + "…"
    return excerpt


def reviewing_banner(document: Optional[Dict]) -> None:
    """Render a persistent 'Currently Reviewing' card using native Streamlit layout."""
    if not document:
        st.info("No document is currently selected. Use the selector below or open a document from the Dashboard.")
        return
    report_type = str(document.get("report_type") or "—")
    fields = [
        ("Company", document.get("company_name", "—")),
        ("SEC Registration No.", document.get("sec_registration_no", "—")),
        ("Period", document.get("period_covered_year", "—")),
        ("Report Type", report_type),
        ("Submission", document.get("submission_type", "—")),
    ]
    if report_type.upper() == "GIS":
        fields[2:2] = [
            ("Corporation Type", document.get("corporation_type", "—")),
            ("Period Covered", document.get("period_covered", "—")),
        ]
    metadata_strip([(label, value, "") for label, value in fields])
