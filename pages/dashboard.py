import pandas as pd
import streamlit as st

from db import query
from storage import get_documents, is_demo_document
from ui_helpers import format_timestamp_pst, metric_card, page_header, recommendation_badge, section_heading, status_badge, timeline_item


REPORT_TYPES = ("AFS", "GIS")
REPORT_VIEW_OPTIONS = ("All Reports", "AFS", "GIS")
OUTCOME_ORDER = (
    "Needs Review",
    "Accepted",
    "Reverted",
    "No Final Recommendation / Pending",
)
ISSUE_STATUSES = ("Warning", "Failed", "Needs Review")
REPORT_TYPE_COLORS = ["#0f5b3f", "#80a98a"]
OUTCOME_COLORS = ["#b28a3a", "#2e7d5b", "#a65a5a", "#78848a"]
ISSUE_COLORS = ["#b28a3a", "#a65a5a", "#78848a"]


def _filtered_documents(documents, report_view):
    if report_view == "All Reports":
        return documents
    return [
        document for document in documents
        if str(document.get("report_type") or "").upper() == report_view
    ]


def _review_outcome(recommendation):
    normalized = str(recommendation or "").strip()
    return {
        "Accept": "Accepted",
        "Revert": "Reverted",
        "Needs Review": "Needs Review",
    }.get(normalized, "No Final Recommendation / Pending")


def _selected_report_types(report_view, documents):
    if report_view == "All Reports":
        return list(REPORT_TYPES)
    return [
        report_view,
    ] if any(
        str(document.get("report_type") or "").upper() == report_view
        for document in documents
    ) else []


def _render_report_view_tiles(documents):
    counts = {
        "All Reports": len(documents),
        "AFS": sum(
            str(document.get("report_type") or "").upper() == "AFS"
            for document in documents
        ),
        "GIS": sum(
            str(document.get("report_type") or "").upper() == "GIS"
            for document in documents
        ),
    }
    report_view = st.session_state.get("dashboard_report_view", "All Reports")
    if report_view not in REPORT_VIEW_OPTIONS:
        report_view = "All Reports"
        st.session_state["dashboard_report_view"] = report_view

    st.markdown("**Report View**")
    columns = st.columns(3)
    labels = (
        ("All Reports", "ALL REPORTS"),
        ("AFS", "AFS REPORTS"),
        ("GIS", "GIS REPORTS"),
    )
    for column, (value, label) in zip(columns, labels):
        with column:
            if st.button(
                label,
                key=f"dashboard_report_view_{value.lower().replace(' ', '_')}",
                type="primary" if report_view == value else "secondary",
                use_container_width=True,
            ):
                if st.session_state.get("dashboard_report_view") != value:
                    st.session_state["dashboard_report_view"] = value
                    st.rerun()
            count = counts[value]
            noun = "Report" if count == 1 else "Reports"
            st.caption(f"{count} {noun}")
    return report_view


def _latest_recommendations():
    rows = query(
        "SELECT document_id, final_recommendation FROM reviewer_actions "
        "WHERE id IN (SELECT MAX(id) FROM reviewer_actions GROUP BY document_id)"
    )
    return {
        row["document_id"]: _review_outcome(row.get("final_recommendation"))
        for row in rows
    }


def _render_summary_cards(report_view, documents, outcomes, validation_rows, figure_rows):
    report_type_counts = {
        report_type: sum(
            str(document.get("report_type") or "").upper() == report_type
            for document in documents
        )
        for report_type in REPORT_TYPES
    }
    selected_ids = {document["id"] for document in documents}
    selected_outcomes = [
        outcomes.get(document["id"], "No Final Recommendation / Pending")
        for document in documents
    ]
    needs_review = sum(
        outcome in {"Needs Review", "No Final Recommendation / Pending"}
        for outcome in selected_outcomes
    )
    accepted = selected_outcomes.count("Accepted")
    reverted = selected_outcomes.count("Reverted")

    if report_view == "All Reports":
        cards = [
            ("Total Reports", len(documents), "All stored AFS and GIS records"),
            ("AFS Reports", report_type_counts["AFS"], "Stored AFS records"),
            ("GIS Reports", report_type_counts["GIS"], "Stored GIS records"),
            ("Needs Review", needs_review, "Needs Review or pending reviewer action"),
            ("Accepted", accepted, "Saved reviewer recommendations"),
            ("Reverted", reverted, "Saved reviewer recommendations"),
        ]
    elif report_view == "AFS":
        afs_figures = [
            row for row in figure_rows
            if row["document_id"] in selected_ids
        ]
        cards = [
            ("AFS Reports", len(documents), "Stored AFS records"),
            ("Needs Review", needs_review, "Needs Review or pending reviewer action"),
            ("Accepted", accepted, "Saved reviewer recommendations"),
            ("Reverted", reverted, "Saved reviewer recommendations"),
            ("Extracted Figures", len(afs_figures), "Stored AFS figure rows"),
            (
                "Corrected Figures / Entries",
                sum(bool(row.get("reviewer_edited")) for row in afs_figures),
                "Reviewer-edited AFS figure rows",
            ),
        ]
    else:
        gis_validations = [
            row for row in validation_rows
            if row["document_id"] in selected_ids
            and str(row.get("report_type") or "").upper() == "GIS"
        ]
        issue_rows = [
            row for row in gis_validations
            if row.get("status") in ISSUE_STATUSES
        ]
        completeness_issues = sum(
            "completeness" in str(row.get("rule_name") or "").lower()
            for row in issue_rows
        )
        quality_orientation_issues = sum(
            any(
                term in str(row.get("rule_name") or "").lower()
                for term in ("quality", "orientation")
            )
            for row in issue_rows
        )
        cards = [
            ("GIS Reports", len(documents), "Stored GIS records"),
            ("Needs Review", needs_review, "Needs Review or pending reviewer action"),
            ("Accepted", accepted, "Saved reviewer recommendations"),
            ("Reverted", reverted, "Saved reviewer recommendations"),
            ("Completeness Issues", completeness_issues, "Warning, failed, or review GIS validations"),
            (
                "Quality / Orientation Issues",
                quality_orientation_issues,
                "Warning, failed, or review GIS validations",
            ),
        ]

    icons = ["▦", "▤", "▥", "!", "✓", "×"]
    columns = st.columns(6)
    for column, card, icon in zip(columns, cards, icons):
        with column:
            metric_card(*card, icon=icon)


def _render_recent_queue(documents, recommendations):
    section_heading("Recent Document Queue", "Stored filings available for reviewer follow-up.", "▤")
    if not documents:
        st.info("No stored documents match the selected Report View.")
        return

    rows = []
    for document in documents:
        rows.append({
            "ID": document["id"],
            "Company Name": document["company_name"],
            "SEC Registration No.": document["sec_registration_no"],
            "Report Type": document["report_type"],
            "Period Covered Year": document["period_covered_year"],
            "Submission Type": document["submission_type"],
            "Recommendation": recommendations.get(
                document["id"],
                "No Final Recommendation / Pending",
            ),
            "Source": "Demo" if is_demo_document(document) else "Uploaded",
            "Uploaded At": format_timestamp_pst(document.get("uploaded_at") or ""),
        })

    display_df = pd.DataFrame(rows)
    st.dataframe(
        display_df,
        width="stretch",
        hide_index=True,
        column_config={
            "ID": st.column_config.NumberColumn("ID", width="small"),
            "Company Name": st.column_config.TextColumn("Company Name"),
            "SEC Registration No.": st.column_config.TextColumn("SEC Registration No."),
            "Report Type": st.column_config.TextColumn("Report Type", width="small"),
            "Period Covered Year": st.column_config.NumberColumn("Period", width="small"),
            "Submission Type": st.column_config.TextColumn("Submission Type", width="medium"),
            "Recommendation": st.column_config.TextColumn("Recommendation", width="medium"),
            "Source": st.column_config.TextColumn("Source", width="small"),
            "Uploaded At": st.column_config.TextColumn("Uploaded At", width="medium"),
        },
    )
    st.markdown(
        "<div style='margin:.4rem 0 .75rem;font-size:.82rem;color:#587267;'>"
        "Recommendations: "
        + recommendation_badge("Accept")
        + "&nbsp;"
        + recommendation_badge("Revert")
        + "&nbsp;"
        + recommendation_badge("Needs Review")
        + "&nbsp;&nbsp;·&nbsp;&nbsp;"
        "<span class='badge' style='background:#f0f0f0;color:#555;font-size:.78rem;padding:.2rem .55rem;'>"
        "Demo</span> = seeded demo document"
        "</div>",
        unsafe_allow_html=True,
    )


def _render_reports_by_type(report_view, documents):
    section_heading("Report Type Distribution", "Counts use currently stored documents only.", "▥")
    selected_types = _selected_report_types(report_view, documents)
    rows = [
        {
            "Report Type": report_type,
            "Reports": sum(
                str(document.get("report_type") or "").upper() == report_type
                for document in documents
            ),
        }
        for report_type in selected_types
    ]
    if not rows:
        st.info("No report-type records are available for this view.")
        return
    chart_df = pd.DataFrame(rows).set_index("Report Type").T
    st.bar_chart(chart_df, height=240, color=REPORT_TYPE_COLORS[:len(chart_df.columns)])


def _render_review_outcomes(report_view, documents, outcomes):
    section_heading("Review Outcomes", "Latest saved reviewer recommendations by report type.", "✓")
    selected_types = _selected_report_types(report_view, documents)
    rows = []
    for report_type in selected_types:
        type_documents = [
            document for document in documents
            if str(document.get("report_type") or "").upper() == report_type
        ]
        type_outcomes = [
            outcomes.get(document["id"], "No Final Recommendation / Pending")
            for document in type_documents
        ]
        rows.append({
            "Report Type": report_type,
            **{
                outcome: type_outcomes.count(outcome)
                for outcome in OUTCOME_ORDER
            },
        })
    if not rows:
        st.info("No reviewer outcomes are available for this view.")
        return
    chart_df = pd.DataFrame(rows).set_index("Report Type")
    st.bar_chart(
        chart_df[list(OUTCOME_ORDER)],
        height=240,
        color=OUTCOME_COLORS,
    )
    st.caption("Pending includes documents without a saved final recommendation.")


def _render_validation_issues(report_view, documents, validation_rows):
    section_heading("Top Validation Issues", "Warning, Failed, and Needs Review validation records.", "!")
    selected_ids = {document["id"] for document in documents}
    rows = [
        row for row in validation_rows
        if row["document_id"] in selected_ids
        and row.get("status") in ISSUE_STATUSES
    ]
    if not rows:
        st.info("No Warning, Failed, or Needs Review validation records are available for this view.")
        return

    issue_df = pd.DataFrame(rows)
    issue_df = (
        issue_df.groupby(["rule_name", "status"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=ISSUE_STATUSES, fill_value=0)
        .sort_values(list(ISSUE_STATUSES), ascending=False)
    )
    issue_df.index.name = "Validation Issue"
    issue_df.columns.name = None
    st.bar_chart(issue_df, height=320, color=ISSUE_COLORS)
    st.caption("Counts are aggregated directly from stored validation results.")


def render():
    page_header(
        "DASHBOARD",
        "Dashboard",
        "Executive overview of AFS and GIS intake, validation, and reviewer operations.",
        "Live DB Data",
    )

    all_documents = get_documents()
    report_view = _render_report_view_tiles(all_documents)
    documents = _filtered_documents(all_documents, report_view)
    recommendations = _latest_recommendations()
    validation_rows = query(
        "SELECT v.document_id, d.report_type, v.rule_name, v.status "
        "FROM validations v JOIN documents d ON d.id = v.document_id"
    )
    figure_rows = query(
        "SELECT f.document_id, f.reviewer_edited "
        "FROM extracted_figures f JOIN documents d ON d.id = f.document_id "
        "WHERE d.report_type = 'AFS'"
    )

    _render_summary_cards(
        report_view,
        documents,
        recommendations,
        validation_rows,
        figure_rows,
    )
    main_col, activity_col = st.columns([2.3, 1], gap="large")
    with main_col:
        _render_recent_queue(documents, recommendations)
    with activity_col:
        section_heading("Recent Stored Activity", "Derived from current document records.", "◷")
        if documents:
            for document in documents[:6]:
                source = "Demo" if is_demo_document(document) else "Uploaded"
                timeline_item(
                    f"{document.get('report_type') or 'Report'} filing available",
                    f"{document.get('company_name')} · {source} · {format_timestamp_pst(document.get('uploaded_at') or '')}",
                    recommendations.get(document["id"], "Pending"),
                )
        else:
            st.info("No stored activity for the selected view.")

    top_left, top_right = st.columns([1, 1])
    with top_left:
        _render_reports_by_type(report_view, documents)
    with top_right:
        _render_review_outcomes(report_view, documents, recommendations)
    _render_validation_issues(report_view, documents, validation_rows)
