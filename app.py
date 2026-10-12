import streamlit as st

from config import APP_TITLE, BASE_DIR
from db import init_db
import pages.dashboard as dashboard
import pages.document_review as document_review
import pages.figures_review as figures_review
import pages.historical_company as historical_company
import pages.rankings as rankings
import pages.settings_demo_data as settings_demo_data
import pages.upload_intake as upload_intake
from storage import ensure_all_demo_documents, get_documents, is_demo_document, seed_company_master

PAGES = {
    "Dashboard": dashboard.render,
    "Upload / Intake": upload_intake.render,
    "Document Review": document_review.render,
    "AFS Figures Extraction Review": figures_review.render,
    "Historical Company View": historical_company.render,
    "Rankings / Research View": rankings.render,
    "Demo Data & Configuration": settings_demo_data.render,
}

AFS_NAV = [
    ("Upload / Intake", "Upload / Intake"),
    ("Document Review", "Document Review"),
    ("Figures Extraction Review", "AFS Figures Extraction Review"),
    ("Historical Company View", "Historical Company View"),
]
GIS_NAV = [
    ("Upload / Intake", "Upload / Intake"),
    ("Document Review", "Document Review"),
]


def apply_styles():
    st.markdown(
        """
        <style>
        :root {
            --primary: #0E5D3F;
            --primary-dark: #06452F;
            --accent: #22C55E;
            --mint: #D9F2E6;
            --bg: #F4F8F6;
            --surface: #FFFFFF;
            --text: #0F172A;
            --muted: #64748B;
            --border: #DCE7E1;
            --warning: #F59E0B;
            --danger: #DC2626;
            --info: #2563EB;
            --shadow: 0 12px 30px rgba(15, 23, 42, .07);
        }
        .stApp { background: radial-gradient(circle at top left, rgba(217,242,230,.9), transparent 28rem), var(--bg); color: var(--text); }
        section[data-testid="stSidebar"] { background: linear-gradient(150deg, #06452F 0%, #0E5D3F 55%, #023827 100%); }
        section[data-testid="stSidebar"]:before {
            content: ""; position: absolute; inset: auto -80px 0 0; height: 250px;
            background: linear-gradient(135deg, transparent 30%, rgba(34,197,94,.16)); pointer-events: none;
        }
        section[data-testid="stSidebar"] * { color: #ffffff !important; }
        section[data-testid="stSidebar"] hr { border-color: rgba(255, 255, 255, .18); }
        section[data-testid="stSidebar"] .stButton button {
            background: transparent;
            border: 1px solid transparent;
            min-height: 2.75rem;
            justify-content: flex-start;
            padding-left: .85rem;
        }
        section[data-testid="stSidebar"] .stButton button:hover { background: rgba(255, 255, 255, .10); border-color: rgba(255, 255, 255, .18); }
        section[data-testid="stSidebar"] .stButton button:disabled {
            background: linear-gradient(90deg, rgba(34,197,94,.35), rgba(34,197,94,.18));
            border-color: rgba(255, 255, 255, .22);
            opacity: 1;
        }
        section[data-testid="stSidebar"] .stButton button:disabled,
        section[data-testid="stSidebar"] .stButton button:disabled * {
            color: #ffffff !important;
        }
        [data-testid="stSidebarNav"] { display: none !important; }
        .main .block-container { padding: .75rem 1.75rem 2.5rem; max-width: 1380px; }
        .app-topbar { display:flex; min-height:58px; align-items:center; justify-content:space-between; gap:1.25rem; margin:0 0 1rem; padding:.55rem .75rem; background:rgba(255,255,255,.8); border:1px solid var(--border); border-radius:14px; box-shadow:0 8px 22px rgba(15,23,42,.05); backdrop-filter:blur(8px); }
        .topbar-search { flex:1; max-width:680px; color:#475569; background:#fff; border:1px solid var(--border); border-radius:10px; padding:.6rem .8rem; font-size:.88rem; }
        .topbar-user { display:flex; align-items:center; gap:.65rem; color:var(--text); font-size:.86rem; white-space:nowrap; }
        .avatar { width:38px; height:38px; border-radius:999px; display:grid; place-items:center; background:var(--primary); color:white; font-weight:800; }
        .sidebar-brand { padding:.55rem .25rem .85rem; border-bottom:1px solid rgba(255,255,255,.18); margin-bottom:.65rem; }
        .sidebar-title { font-size:1.26rem; font-weight:800; line-height:1.15; }
        .sidebar-subtitle { color:rgba(255,255,255,.76) !important; font-size:.86rem; margin-top:.35rem; }
        .sidebar-group { font-size:.7rem; font-weight:800; letter-spacing:.12em; margin:.8rem .15rem .3rem; color:rgba(255,255,255,.82) !important; }
        .sidebar-footer { margin-top:1.25rem; color:rgba(255,255,255,.78) !important; font-size:.8rem; border-top:1px solid rgba(255,255,255,.18); padding:.75rem .25rem 0; }
        .page-header { margin:.05rem 0 .8rem; }
        .eyebrow { color:#475569; font-size:.78rem; letter-spacing:.14em; text-transform:uppercase; font-weight:800; margin-bottom:.2rem; }
        .page-title-row { display:flex; align-items:center; gap:.8rem; flex-wrap:wrap; }
        .page-title-row h1 { margin:0; font-size:2.15rem; line-height:1.1; color:var(--text); letter-spacing:-.035em; }
        .page-header p { margin:.35rem 0 0; color:var(--muted); font-size:1rem; }
        .page-badge { background:var(--mint); color:var(--primary); border-radius:999px; padding:.3rem .7rem; font-weight:800; font-size:.78rem; }
        .metric-card, .soft-card, div[data-testid="stVerticalBlockBorderWrapper"] { background:var(--surface); border-color:var(--border) !important; border-radius:16px !important; box-shadow:var(--shadow); }
        .metric-card { border:1px solid var(--border); padding:.85rem; min-height:104px; }
        .metric-card-top { display:flex; justify-content:space-between; gap:.75rem; align-items:flex-start; }
        .metric-icon, .section-icon, .info-card-icon { min-width:36px; width:36px; height:36px; border-radius:10px; display:grid; place-items:center; background:var(--mint); color:var(--primary); font-weight:900; }
        .metric-label { color:#334155; font-size:.78rem; font-weight:800; }
        .metric-value { color:var(--text); font-size:1.75rem; font-weight:850; margin-top:.35rem; line-height:1.05; }
        .metric-caption { color:var(--muted); font-size:.82rem; margin-top:.35rem; }
        .badge { display:inline-block; border-radius:999px; font-size:.78rem; font-weight:800; padding:.22rem .62rem; margin:.1rem .2rem .1rem 0; white-space:nowrap; }
        .info-card { display:flex; align-items:center; gap:.75rem; background:linear-gradient(90deg,#EAF7EF,#F6FFFA); border:1px solid var(--border); border-radius:14px; padding:.8rem .9rem; box-shadow:var(--shadow); }
        .info-card span { color:var(--muted); font-size:.86rem; }
        .section-heading { display:flex; gap:.7rem; align-items:flex-start; margin:.2rem 0 .6rem; }
        .section-heading h3 { margin:0; color:var(--text); font-size:1.05rem; }
        .section-heading p { margin:.15rem 0 0; color:var(--muted); font-size:.86rem; }
        .metadata-strip { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:0; background:#fff; border:1px solid var(--border); border-radius:14px; box-shadow:var(--shadow); margin:.35rem 0 .8rem; overflow:hidden; }
        .metadata-item { display:flex; gap:.7rem; align-items:center; padding:.8rem; border-right:1px solid var(--border); }
        .metadata-item span { display:block; color:var(--muted); font-size:.76rem; font-weight:700; }
        .metadata-item strong { display:block; color:var(--text); font-size:.9rem; margin-top:.12rem; }
        .metadata-icon { color:var(--primary); font-weight:900; }
        .validation-card { background:#fff; border:1px solid var(--border); border-left:4px solid var(--primary); border-radius:14px; padding:.85rem 1rem; margin-bottom:.65rem; box-shadow:0 8px 18px rgba(15,23,42,.045); }
        .validation-card p { color:#334155; margin:.45rem 0 .1rem; font-size:.88rem; }
        .validation-card small { color:var(--muted); }
        .timeline-item { position:relative; display:flex; gap:.75rem; padding:.35rem 0 .85rem; color:var(--text); }
        .timeline-item span { color:var(--muted); font-size:.82rem; }
        .timeline-dot { min-width:12px; width:12px; height:12px; border-radius:999px; margin-top:.3rem; box-shadow:0 0 0 4px rgba(14,93,63,.1); }
        .empty-state { background:#fff; border:1px dashed var(--border); border-radius:16px; padding:1.25rem; color:var(--muted); text-align:center; }
        .empty-state strong { color:var(--text); }
        .text-preview { background:#ffffff; border:1px solid var(--border); border-left:4px solid var(--primary); border-radius:12px; padding:1rem; line-height:1.65; color:var(--text); }
        mark { background:#DFF6CB; color:var(--primary-dark); padding:.08rem .2rem; border-radius:4px; }
        div[data-testid="stDataFrame"] { border:1px solid var(--border); border-radius:14px; overflow:hidden; box-shadow:0 8px 18px rgba(15,23,42,.04); }
        [data-testid="stFileUploaderDropzone"] { min-height:132px; padding:1.25rem; background:linear-gradient(135deg,#F7FCF9,#ECF8F1); border:1.5px dashed #84C9A8; border-radius:14px; }
        [data-testid="stFileUploaderDropzone"] button { border-radius:9px; }
        .stButton button, .stDownloadButton button { border-radius:10px; font-weight:800; min-height:2.55rem; }
        h1, h2, h3 { color:var(--text); }
        [data-testid="stMetric"] { background:#fff; border:1px solid var(--border); border-radius:16px; padding:1rem; box-shadow:var(--shadow); }
        @media (max-width: 900px) {
            .main .block-container { padding:.65rem 1rem 2rem; }
            .app-topbar { align-items:stretch; flex-direction:column; }
            .topbar-search { max-width:none; }
            .page-title-row h1 { font-size:1.8rem; }
            .metadata-strip { grid-template-columns:1fr 1fr; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def bootstrap():
    init_db()
    seed_company_master()
    if "active_document_id" not in st.session_state:
        st.session_state["active_document_id"] = ensure_all_demo_documents()


def _navigate(page: str, context: str = None) -> None:
    st.session_state["_current_page"] = page
    if context:
        st.session_state["review_context"] = context
        if page == "Upload / Intake":
            st.session_state["intake_report_type"] = context
    st.rerun()


def _sidebar_nav_button(label: str, page: str, context: str = None) -> None:
    active = (
        st.session_state.get("_current_page") == page
        and (context is None or st.session_state.get("review_context") == context)
    )
    if st.sidebar.button(
        label,
        key=f"nav_{context or 'main'}_{page}",
        type="primary" if active else "secondary",
        use_container_width=True,
        disabled=active,
    ):
        _navigate(page, context)


def _render_sidebar_navigation() -> None:
    st.sidebar.markdown('<div class="sidebar-group">MAIN</div>', unsafe_allow_html=True)
    _sidebar_nav_button("Dashboard", "Dashboard")

    st.sidebar.markdown('<div class="sidebar-group">AFS REPORTS</div>', unsafe_allow_html=True)
    for label, page in AFS_NAV:
        _sidebar_nav_button(label, page, "AFS")

    st.sidebar.markdown('<div class="sidebar-group">GIS REPORTS</div>', unsafe_allow_html=True)
    for label, page in GIS_NAV:
        _sidebar_nav_button(label, page, "GIS")

    st.sidebar.markdown('<div class="sidebar-group">RESEARCH</div>', unsafe_allow_html=True)
    _sidebar_nav_button("Rankings / Research View", "Rankings / Research View")

    st.sidebar.markdown('<div class="sidebar-group">PROTOTYPE ADMIN</div>', unsafe_allow_html=True)
    _sidebar_nav_button("Demo Data & Configuration", "Demo Data & Configuration")


def _render_top_bar() -> None:
    st.markdown(
        """
        <div class="app-topbar">
            <div class="topbar-search">Search companies, filings, or reference numbers... <span style="float:right;color:#94A3B8;">Ctrl K</span></div>
            <div class="topbar-user"><span style="color:#DC2626;">●</span><div class="avatar">JD</div><div><strong>John Dela Cruz</strong><br><span style="color:#64748B;">SEC Staff</span></div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_demo_documents() -> None:
    st.sidebar.divider()
    st.sidebar.markdown("**DEMO DOCUMENTS**")
    demo_documents = [document for document in get_documents() if is_demo_document(document)]
    afs_documents = [document for document in demo_documents if document.get("report_type") == "AFS"]
    gis_documents = [document for document in demo_documents if document.get("report_type") == "GIS"]
    if afs_documents:
        st.sidebar.caption("AFS")
        for document in afs_documents:
            st.sidebar.write(
                f"• {document['company_name']} — {document['period_covered_year']}"
            )
    if gis_documents:
        st.sidebar.caption("GIS")
        for document in gis_documents:
            corporation_type = document.get("corporation_type") or "GIS"
            st.sidebar.write(
                f"• {document['company_name']} — {document['period_covered_year']} {corporation_type} GIS"
            )


def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    apply_styles()
    bootstrap()
    st.sidebar.image(str(BASE_DIR / "assets" / "efast-checker-icon.png"), width=72)
    st.sidebar.markdown(
        f"""
        <div class="sidebar-brand">
            <div class="sidebar-title">{APP_TITLE}</div>
            <div class="sidebar-subtitle">GIS & AFS Reviewer Assistance</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if "_current_page" not in st.session_state:
        st.session_state["_current_page"] = "Dashboard"
    if "review_context" not in st.session_state:
        st.session_state["review_context"] = "AFS"

    _render_sidebar_navigation()
    _render_demo_documents()
    st.sidebar.markdown('<div class="sidebar-footer">ⓘ&nbsp;&nbsp;Version 1.0.0</div>', unsafe_allow_html=True)

    _render_top_bar()
    PAGES[st.session_state["_current_page"]]()


if __name__ == "__main__":
    main()
