import pandas as pd
import streamlit as st

from config import RANKING_METRICS
from storage import load_demo_data
from ui_helpers import dataframe_download, format_peso, metric_card, page_header, section_heading


def render():
    page_header(
        "RESEARCH",
        "Rankings / Research View",
        "Seeded research prototype for ranked company extraction and institutional review use cases.",
        "Seeded Prototype",
    )

    st.info(
        "**Demo Projection** — Rankings are currently based on seeded demo data and must not be presented as official SEC rankings. "
        "In future phases, this view will rank companies using figures extracted and reviewed across uploaded filings."
    )

    demo = load_demo_data()
    df = pd.DataFrame(demo["ranking_data"])
    filter_cols = st.columns([1.5, .7])
    metric = filter_cols[0].selectbox("Ranking Metric", RANKING_METRICS, index=0)
    ranked = df.sort_values(metric, ascending=False).reset_index(drop=True)
    ranked.insert(0, "Rank", ranked.index + 1)
    ranked["Display Value"] = ranked[metric].map(format_peso)

    with filter_cols[1]:
        dataframe_download(ranked, f"research_ranking_{metric.lower().replace(' ', '_')}.csv", "Export CSV")
    metric_card("Highest Ranked Company", ranked.iloc[0]["company_name"], ranked.iloc[0]["Display Value"], "▥")
    section_heading("Seeded Ranking Table", "Prototype data only; values are not official SEC rankings.", "▤")
    st.dataframe(ranked[["Rank", "company_name", "sec_registration_no", metric, "Display Value"]], width="stretch", hide_index=True)
    section_heading("Ranking Chart", f"Companies sorted by {metric} from seeded demo data.", "▥")
    st.bar_chart(ranked.set_index("company_name")[metric], color="#0f5b3f")
