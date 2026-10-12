import pandas as pd
import streamlit as st

from storage import load_company_master, load_demo_data
from ui_helpers import dataframe_download, format_peso, page_header, section_heading


def render():
    page_header(
        "AFS REPORTS",
        "Historical Company View",
        "Multi-year company financial trends and reusable normalized data.",
        "Demo Projection",
    )

    master = load_company_master()
    demo = load_demo_data()
    df = pd.DataFrame(demo["historical_data"])

    st.info(
        "**Demo Projection** — This view is currently based on seeded demo data and does not yet reflect "
        "live uploaded extraction data."
    )
    filter_cols = st.columns([1.4, 1, 1, .8])
    filter_cols[0].selectbox("Company", [master["company_name"]])
    filter_cols[1].selectbox("Year Range", [f"{df['year'].min()} - {df['year'].max()}"])
    filter_cols[2].selectbox("Key Metric", ["All Key Metrics", "Gross Revenue", "Net Income", "Total Assets"])
    with filter_cols[3]:
        dataframe_download(df, "audentia_fortuna_historical_figures.csv", "Export CSV")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("SEC Registration No.", master["sec_registration_no"])
    c2.metric("Coverage", f"{df['year'].min()}–{df['year'].max()}")
    c3.metric("Latest Total Assets", format_peso(df.iloc[-1]["Total Assets"]))
    latest_income = format_peso(df.iloc[-1]["Net Income"])
    c4.metric("Latest Net Income", latest_income)

    section_heading("Trend Charts", "Seeded projection data for presentation and workflow context.", "▥")
    chart_df = df.set_index("year")
    st.line_chart(chart_df[["Gross Revenue", "Total Assets", "Net Income"]], height=280, color=["#0f5b3f", "#2e8b57", "#90c4a4"])
    section_heading("Financial Trend (Normalized Data)", "Seeded demo values remain clearly labeled as projection data.", "▤")
    st.dataframe(df, width="stretch", hide_index=True)
