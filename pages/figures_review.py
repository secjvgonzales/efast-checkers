import math

import pandas as pd
import streamlit as st

from confidence import CONFIDENCE_WEIGHTS, calculate_figure_confidence
from db import update_figure_reviews
from extraction_engine import MANDATORY_LABELS, fiscal_year_candidates, page_scope, select_preferred_figures
from storage import get_document, get_documents, get_figures, get_pages
from ui_helpers import clean_source_snippet, dataframe_download, format_peso, metric_card, reviewing_banner, show_document_selector
from validation_engine import detect_afs_reporting_years

REVENUE_LABELS = {"gross_revenue", "total_revenue", "revenue"}


def _confidence_display(score, classification) -> str:
    """Format a computed 0–100 score for reviewer display."""
    try:
        value = int(score)
        if value < 0 or value > 100:
            return "—"
        return f"{value}% · {classification}"
    except (TypeError, ValueError):
        return "—"


def _current_revenue_value(df: pd.DataFrame, current_year):
    if current_year is None:
        return None
    current_revenue = df[
        (df["fiscal_year"] == current_year)
        & (df["normalized_label"].isin(REVENUE_LABELS))
    ]["normalized_peso_value"].dropna()
    current_revenue = current_revenue[
        current_revenue.apply(lambda value: not math.isnan(float(value)) if value is not None else False)
    ]
    return current_revenue.max() if not current_revenue.empty else None


def _normalized_figure_buckets(df: pd.DataFrame, current_year) -> pd.DataFrame:
    bucket_source = df.dropna(subset=["normalized_peso_value"]).copy()
    if bucket_source.empty:
        return pd.DataFrame(columns=["Field", "Fiscal Year", "Year Role", "Total (₱)"])
    bucket_source["Fiscal Year"] = bucket_source["fiscal_year"].astype(int)
    bucket_source["Year Role"] = bucket_source["Fiscal Year"].apply(
        lambda year: "Current" if current_year is not None and year == current_year else "Comparative"
    )
    bucket = (
        bucket_source.groupby(["normalized_label", "Fiscal Year", "Year Role"], as_index=False)["normalized_peso_value"]
        .sum()
        .sort_values("normalized_peso_value", ascending=False)
    )
    return bucket.rename(columns={"normalized_label": "Field", "normalized_peso_value": "Total (₱)"})


def render():
    st.header("AFS Figures Extraction Review")
    st.caption("Hero workflow for structured extraction, reviewer correction, and database-ready AFS financial figures.")

    documents = [
        document for document in get_documents()
        if str(document.get("report_type") or "").upper() == "AFS"
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
        active_id = show_document_selector(documents, "figures_doc_selector")
        if not active_id:
            return
        st.session_state["active_document_id"] = active_id
    else:
        with st.expander("Switch document", expanded=False):
            switched_id = show_document_selector(documents, "figures_doc_switcher")
            if switched_id and switched_id != active_id:
                if st.button("Load selected document", key="figures_switch_btn"):
                    st.session_state["active_document_id"] = switched_id
                    st.rerun()

    document_id = st.session_state["active_document_id"]
    document = get_document(document_id)

    if not document:
        st.warning("Selected document was not found. Please choose another document.")
        st.session_state.pop("active_document_id", None)
        return

    # ── Persistent "Currently Reviewing" banner ──────────────────────────────
    reviewing_banner(document)

    pages = get_pages(document_id)
    detected_reporting_years = detect_afs_reporting_years(pages)
    current_year = detected_reporting_years[0] if detected_reporting_years else int(document["period_covered_year"]) if document.get("period_covered_year") else None
    reporting_years = detected_reporting_years or fiscal_year_candidates(document)
    reporting_years_display = " · ".join(str(year) for year in reporting_years) if reporting_years else "—"
    st.markdown(f"**Reporting Years:** {reporting_years_display}")
    if reporting_years:
        st.caption(
            " · ".join(
                f"{year} = {'Current' if year == current_year else 'Comparative'}"
                for year in reporting_years
            )
        )

    figures = get_figures(document_id)
    if not figures:
        st.warning("No supported financial figures were reliably extracted from this document.")
        return

    df = pd.DataFrame(figures)
    pages_by_number = {
        int(page["page_number"]): page
        for page in pages
        if page.get("page_number") is not None
    }
    enriched_figures = []
    for row in figures:
        enriched = dict(row)
        page = pages_by_number.get(int(row["page_number"])) if row.get("page_number") is not None else None
        if page:
            page_text = page.get("extracted_text") or page.get("original_text") or page.get("text_preview") or ""
            enriched["source_scope"] = page_scope(page_text)
        enriched_figures.append(enriched)
    preferred_figures = select_preferred_figures(enriched_figures)
    preferred_ids = {row.get("id") for row in preferred_figures if row.get("id") is not None}
    preferred_df = pd.DataFrame(preferred_figures) if preferred_figures else df.iloc[0:0].copy()
    computed_by_id = {}
    for row in figures:
        page = pages_by_number.get(int(row["page_number"])) if row.get("page_number") is not None else None
        evidence_row = {**row, "_mandatory_labels": MANDATORY_LABELS}
        computed_by_id[row["id"]] = calculate_figure_confidence(evidence_row, page)

    def effective_review_status(row):
        computed = computed_by_id.get(row["id"], {})
        stored_status = row.get("review_status") or "Needs Review"
        if row.get("reviewer_edited") or stored_status in {"Reviewed", "Corrected", "Rejected"}:
            return stored_status
        return computed.get("initial_review_status", stored_status)

    df["computed_confidence_score"] = df["id"].map(
        lambda figure_id: computed_by_id.get(figure_id, {}).get("score")
    )
    df["confidence_classification"] = df["id"].map(
        lambda figure_id: computed_by_id.get(figure_id, {}).get("classification", "Low")
    )
    df["computed_review_status"] = df.apply(effective_review_status, axis=1)
    check_source_count = int((df["computed_review_status"] == "Check Source").sum())
    if check_source_count:
        st.warning(
            f"{check_source_count} figure row(s) have **Check Source** status. "
            "Low-confidence or safety-capped evidence requires source verification. Ambiguous raw values are "
            "retained and normalized peso values remain blank rather than being repaired automatically."
        )

    available_years = sorted(
        set(df["fiscal_year"].dropna().astype(int).unique())
        | set(reporting_years),
        reverse=True,
    )
    year_options = ["All Years"] + [
        f"{year} — {'Current' if year == current_year else 'Comparative'}"
        for year in available_years
    ]
    selected_year = st.selectbox(
        "View Fiscal Year",
        year_options,
        key=f"figures_year_filter_{document_id}",
    )
    selected_year_value = None if selected_year == "All Years" else int(selected_year.split(" ", 1)[0])
    view_df = df if selected_year_value is None else df[df["fiscal_year"] == selected_year_value].copy()

    # Current Revenue is intentionally limited to the document's Period Covered Year.
    current_revenue = _current_revenue_value(preferred_df, current_year)
    rev_display = format_peso(current_revenue) if current_revenue is not None else "No detected revenue"

    fiscal_years_display = " · ".join(str(year) for year in reporting_years) if reporting_years else "—"

    needs_review_count = int(df["computed_review_status"].isin(["Needs Review", "Check Source"]).sum())

    hero_cols = st.columns(5)
    with hero_cols[0]:
        metric_card("Rows Extracted", len(df), "Ready for reviewer validation")
    with hero_cols[1]:
        metric_card("Normalized Fields", df["normalized_label"].nunique(), "Reusable figure buckets")
    with hero_cols[2]:
        metric_card("Fiscal Years", fiscal_years_display, "Current and comparative")
    with hero_cols[3]:
        metric_card("Current Revenue", rev_display, "Normalized peso value")
    with hero_cols[4]:
        metric_card("Needs Review", needs_review_count, "Rows pending reviewer action")

    if view_df.empty:
        st.info(
            f"No extracted figures are available for fiscal year {selected_year_value}. "
            "No comparative values were generated for this year."
        )
        return

    st.subheader(f"Extracted Figures Review Table — {document['company_name']}")
    st.caption(
        "Computed confidence uses deterministic prototype rules — it is not an ML probability. "
        "Review and correct as needed before treating figures as authoritative."
    )

    # Build editable view — sort Needs Review rows to the top for easy scanning
    review_cols = [
        "id", "page_number", "statement_type", "raw_label", "normalized_label",
        "fiscal_year", "displayed_value", "normalized_peso_value", "unit_basis",
        "source_snippet", "confidence", "review_status", "reviewer_edited", "reviewed_value",
    ]
    editable = view_df[review_cols].copy()
    editable["reviewed_value"] = editable["reviewed_value"].fillna("")
    editable["year_role"] = editable["fiscal_year"].apply(
        lambda year: "Current" if current_year is not None and int(year) == current_year else "Comparative"
    )

    editable["computed_confidence_score"] = editable["id"].map(df.set_index("id")["computed_confidence_score"])
    editable["confidence_classification"] = editable["id"].map(df.set_index("id")["confidence_classification"])
    editable["computed_review_status"] = editable.apply(effective_review_status, axis=1)
    editable["conf_display"] = editable.apply(
        lambda row: _confidence_display(row["computed_confidence_score"], row["confidence_classification"]),
        axis=1,
    )
    editable["review_status"] = editable["computed_review_status"]

    # Sort: Needs Review first, then by page_number
    sort_key = editable["review_status"].apply(lambda s: 0 if s in ("Needs Review", "Check Source") else 1)
    editable = editable.assign(_sort=sort_key).sort_values(["_sort", "page_number"]).drop(columns=["_sort"])

    # Keep reviewer actions near confidence; source details remain in the explanation panel and export.
    display_cols = [
        "id", "page_number", "raw_label", "fiscal_year", "year_role",
        "displayed_value", "conf_display", "review_status", "reviewed_value",
        "normalized_label", "normalized_peso_value", "reviewer_edited",
    ]
    editable_view = editable[display_cols].copy()
    editable_view["normalized_peso_value"] = editable_view["normalized_peso_value"].map(format_peso)

    edited = st.data_editor(
        editable_view,
        width="stretch",
        hide_index=True,
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
            "page_number": st.column_config.NumberColumn("Page", disabled=True, width="small"),
            "raw_label": st.column_config.TextColumn("Raw Label", disabled=True),
            "normalized_label": st.column_config.TextColumn("Normalized Label", disabled=True),
            "fiscal_year": st.column_config.NumberColumn("Fiscal Year", disabled=True, width="small"),
            "year_role": st.column_config.TextColumn("Year Role", disabled=True, width="small"),
            "displayed_value": st.column_config.TextColumn("Displayed Value", disabled=True),
            "normalized_peso_value": st.column_config.TextColumn("Normalized (₱)", disabled=True),
            "conf_display": st.column_config.TextColumn("Computed Confidence", disabled=True, width="medium"),
            "review_status": st.column_config.SelectboxColumn(
                "Review Status", options=[
                    "Ready for Quick Validation", "Needs Review", "Check Source",
                    "Reviewed", "Corrected", "Rejected",
                ]
            ),
            "reviewer_edited": st.column_config.CheckboxColumn("Edited?", disabled=True, width="small"),
            "reviewed_value": st.column_config.TextColumn("Reviewed / Corrected Value"),
        },
    )

    with st.expander("Explain Computed Confidence", expanded=False):
        explanation_ids = editable["id"].tolist()
        if explanation_ids:
            selected_explanation_id = st.selectbox(
                "Figure row",
                explanation_ids,
                format_func=lambda figure_id: (
                    f"#{figure_id} — "
                    f"{editable.loc[editable['id'] == figure_id, 'raw_label'].iloc[0]} "
                    f"({editable.loc[editable['id'] == figure_id, 'fiscal_year'].iloc[0]})"
                ),
                key=f"confidence_explanation_{document_id}",
            )
            selected_computed = computed_by_id.get(selected_explanation_id)
            if selected_computed:
                st.markdown(
                    f"**Computed Confidence: {selected_computed['score']}% · "
                    f"{selected_computed['classification']}**"
                )
                st.caption(
                    "Confidence is calculated from deterministic prototype rules and is not an ML probability. "
                    f"Initial routing: {selected_computed['initial_review_status']}."
                )
                selected_row = editable.loc[editable["id"] == selected_explanation_id].iloc[0]
                st.caption(
                    f"Page {int(selected_row['page_number'])} · "
                    f"Unit basis: {selected_row['unit_basis']} · "
                    f"Displayed value: {selected_row['displayed_value']}"
                )
                breakdown = selected_computed["breakdown"]
                st.markdown(
                    "\n".join(
                        f"- **{factor}:** {points}/{weight}"
                        for factor, points in breakdown.items()
                        for weight in [CONFIDENCE_WEIGHTS.get(factor, 0)]
                    )
                )
                if selected_computed["caps"]:
                    st.caption("Safety cap applied: " + "; ".join(selected_computed["caps"]) + ".")
                source_page = pages_by_number.get(int(selected_row["page_number"])) or {}
                st.code(
                    clean_source_snippet(
                        selected_row["source_snippet"],
                        context=source_page.get("text_preview", ""),
                        anchor=selected_row["raw_label"],
                    ) or "No source snippet available.",
                    language=None,
                )

    with st.expander("Review / Correct Selected Figure", expanded=False):
        review_ids = editable["id"].tolist()
        if review_ids:
            selected_review_id = st.selectbox(
                "Figure row to review",
                review_ids,
                format_func=lambda figure_id: (
                    f"#{figure_id} — "
                    f"{editable.loc[editable['id'] == figure_id, 'raw_label'].iloc[0]} "
                    f"({editable.loc[editable['id'] == figure_id, 'fiscal_year'].iloc[0]})"
                ),
                key=f"figure_review_selector_{document_id}",
            )
            selected_review_row = editable.loc[editable["id"] == selected_review_id].iloc[0]
            status_options = [
                "Ready for Quick Validation", "Needs Review", "Check Source",
                "Reviewed", "Corrected", "Rejected",
            ]
            current_status = str(selected_review_row["review_status"] or "Needs Review")
            with st.form(f"selected_figure_review_form_{document_id}_{selected_review_id}"):
                selected_status = st.selectbox(
                    "Review Status",
                    status_options,
                    index=status_options.index(current_status) if current_status in status_options else 1,
                )
                corrected_value = st.text_input(
                    "Reviewed / Corrected Value",
                    value=str(selected_review_row["reviewed_value"] or ""),
                    placeholder=str(selected_review_row["displayed_value"] or ""),
                )
                if st.form_submit_button("Save Selected Figure Review", type="primary"):
                    update_figure_reviews(document_id, [{
                        "id": selected_review_id,
                        "displayed_value": selected_review_row["displayed_value"],
                        "reviewed_value": corrected_value,
                        "review_status": selected_status,
                    }])
                    st.success("Selected figure review saved.")

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("Save Corrections", type="primary"):
            # Map edits back using the original df index via id column
            records = edited.rename(columns={"conf_display": "confidence"}).to_dict("records")
            stored_by_id = {row["id"]: row for row in figures}
            computed_status_by_id = dict(zip(editable["id"], editable["computed_review_status"]))
            for r in records:
                original = stored_by_id.get(r["id"], {})
                if (
                    not original.get("reviewer_edited")
                    and r.get("review_status") == computed_status_by_id.get(r["id"])
                    and original.get("review_status") != r.get("review_status")
                ):
                    r["review_status"] = original.get("review_status") or r["review_status"]
            update_figure_reviews(document_id, records)
            st.success("Figure review updates saved.")
    with col2:
        export_columns = [
            "page_number", "statement_type", "raw_label", "normalized_label",
            "fiscal_year", "year_role", "displayed_value", "normalized_peso_value",
            "unit_basis", "source_snippet", "computed_confidence_score",
            "confidence_classification", "review_status", "reviewer_edited", "reviewed_value",
        ]
        export_df = editable[export_columns].copy()
        dataframe_download(export_df, f"sec_efast_figures_document_{document_id}.csv", "Export Figures CSV")

    st.subheader("Normalized Figure Buckets")
    bucket_source = view_df[view_df["id"].isin(preferred_ids)].copy() if preferred_ids and "id" in view_df else view_df
    bucket = _normalized_figure_buckets(bucket_source, current_year)
    if bucket.empty:
        st.info("No safely normalized peso values are available for aggregation yet.")
    else:
        bucket_display = bucket.copy()
        bucket_display["Total (₱)"] = bucket_display["Total (₱)"].map(format_peso)
        st.dataframe(
            bucket_display,
            width="stretch",
            hide_index=True,
            column_config={
                "Fiscal Year": st.column_config.NumberColumn("Fiscal Year", format="%d"),
                "Total (₱)": st.column_config.TextColumn("Total (₱)"),
            },
        )
