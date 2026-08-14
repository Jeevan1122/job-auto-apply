"""
Job Application Agent — Streamlit UI
Daily agent: search → score → list jobs → you apply manually → track everything
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path

import streamlit as st

# Inject Streamlit Cloud secrets into env vars before any other imports read them
try:
    for _k, _v in st.secrets.items():
        os.environ.setdefault(_k, str(_v))
except Exception:
    pass

import pandas as pd

from config import (
    UPLOADS_DIR, MIN_RELEVANCE_SCORE,
    MAX_JOBS_PER_RUN, JOB_TYPES,
    DAILY_RUN_HOUR, DAILY_RUN_MINUTE,
)
from database import (
    init_db, save_resume_profile, get_latest_resume_profile,
    get_all_resume_profiles, get_all_jobs, get_today_stats,
    get_all_daily_summaries, update_job_status,
    mark_manually_applied, unmark_manually_applied, get_manually_applied_jobs,
    set_primary_resume, delete_resume_profile, reset_today_statuses,
)
from resume_parser import parse_resume

st.set_page_config(
    page_title="JobAgent — AI Job Search",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()
TODAY = date.today().isoformat()

# ── Global CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Fonts & base ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

/* ── Page background & default text ── */
.stApp { background: #0D1117 !important; color: #E2E8F0 !important; }
.stApp p, .stApp li, .stApp span, .stApp div { color: #CBD5E1; }
.stApp label { color: #94A3B8 !important; }
.stMarkdown, .stMarkdown p, .stMarkdown li { color: #CBD5E1 !important; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0A0F1E 0%, #0F1F3D 100%) !important;
    border-right: 1px solid rgba(255,255,255,0.07) !important;
}
[data-testid="stSidebar"] * { color: #CBD5E1 !important; }
[data-testid="stSidebar"] .stMarkdown strong { color: #FFFFFF !important; }
[data-testid="stSidebar"] [data-testid="stMetric"] {
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.09);
    border-radius: 10px;
    padding: 10px 12px;
}
[data-testid="stSidebar"] [data-testid="stMetricValue"] { color: #FFFFFF !important; font-size: 1.4rem !important; }
[data-testid="stSidebar"] [data-testid="stMetricLabel"] { color: #64748B !important; font-size: 0.72rem !important; }
[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.08) !important; }
[data-testid="stSidebar"] .stButton > button {
    background: rgba(255,255,255,0.07) !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    color: #CBD5E1 !important;
    border-radius: 8px !important;
    font-size: 0.8rem !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,0.14) !important;
    color: #FFFFFF !important;
}

/* ── Tab bar ── */
.stTabs [data-baseweb="tab-list"] {
    background: #161B27;
    border-radius: 12px;
    padding: 4px 6px;
    gap: 2px;
    border: 1px solid rgba(255,255,255,0.07);
    margin-bottom: 20px;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    padding: 8px 18px;
    font-weight: 500;
    font-size: 0.88rem;
    color: #64748B !important;
    border: none !important;
    background: transparent !important;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #1E3A5F, #2563EB) !important;
    color: #FFFFFF !important;
}
.stTabs [data-baseweb="tab-border"]     { display: none !important; }
.stTabs [data-baseweb="tab-highlight"]  { display: none !important; }

/* ── Job / form cards ── */
[data-testid="stVerticalBlock"] > [data-testid="stVerticalBlock"] > div > [data-testid="stForm"] {
    background: #161B27;
    border-radius: 14px;
    border: 1px solid rgba(255,255,255,0.08);
    padding: 4px 12px;
}

/* ── Metric tiles (main area) ── */
[data-testid="stMetric"] {
    background: #161B27 !important;
    border-radius: 12px;
    padding: 16px 20px;
    border: 1px solid rgba(255,255,255,0.08) !important;
    box-shadow: 0 1px 6px rgba(0,0,0,0.3) !important;
}
[data-testid="stMetricValue"] { font-size: 1.8rem !important; font-weight: 700; color: #F1F5F9 !important; }
[data-testid="stMetricLabel"] { font-size: 0.78rem !important; font-weight: 500; color: #64748B !important; text-transform: uppercase; letter-spacing: 0.04em; }

/* ── Buttons ── */
.stButton > button {
    border-radius: 9px !important;
    font-weight: 600 !important;
    font-size: 0.875rem !important;
    padding: 8px 18px !important;
    transition: all 0.18s ease !important;
    background: #1E2535 !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    color: #CBD5E1 !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #1E3A5F, #2563EB) !important;
    color: #FFFFFF !important;
    border: none !important;
    box-shadow: 0 2px 8px rgba(37,99,235,0.40) !important;
}
.stButton > button[kind="primary"]:hover {
    box-shadow: 0 4px 16px rgba(37,99,235,0.55) !important;
    transform: translateY(-1px) !important;
}
.stButton > button:not([kind="primary"]):hover {
    background: #252D40 !important;
    border-color: rgba(255,255,255,0.22) !important;
    color: #FFFFFF !important;
}

/* ── Download buttons ── */
[data-testid="stDownloadButton"] > button {
    background: #1E2535 !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    color: #93C5FD !important;
    font-weight: 600 !important;
    border-radius: 9px !important;
}
[data-testid="stDownloadButton"] > button:hover {
    background: #1E3A5F !important;
    border-color: #2563EB !important;
    color: #FFFFFF !important;
}

/* ── Text inputs & number inputs ── */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea {
    border-radius: 8px !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    font-size: 0.875rem !important;
    background: #1A2035 !important;
    color: #E2E8F0 !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stNumberInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
    border-color: #2563EB !important;
    box-shadow: 0 0 0 3px rgba(37,99,235,0.20) !important;
}

/* ── Selectbox ── */
[data-testid="stSelectbox"] > div > div {
    border-radius: 8px !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    background: #1A2035 !important;
    color: #E2E8F0 !important;
}

/* ── Multiselect ── */
[data-testid="stMultiSelect"] > div > div {
    background: #1A2035 !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 8px !important;
}

/* ── Slider ── */
[data-testid="stSlider"] { padding: 4px 0 8px 0 !important; }
[data-testid="stSlider"] [data-baseweb="slider"] > div:first-child {
    background: #2D3748 !important;
    border-radius: 999px !important;
    height: 6px !important;
}
[data-testid="stSlider"] [data-baseweb="slider"] [data-testid="stSliderTrackFill"] {
    background: linear-gradient(90deg, #3B82F6, #2563EB) !important;
    border-radius: 999px !important;
    height: 6px !important;
}
[data-testid="stSlider"] [data-baseweb="slider"] [role="slider"] {
    background: #1E2535 !important;
    border: 2.5px solid #3B82F6 !important;
    border-radius: 50% !important;
    width: 20px !important;
    height: 20px !important;
    box-shadow: 0 2px 8px rgba(59,130,246,0.40) !important;
    transition: box-shadow 0.15s ease, transform 0.15s ease !important;
}
[data-testid="stSlider"] [data-baseweb="slider"] [role="slider"]:hover {
    box-shadow: 0 0 0 6px rgba(59,130,246,0.20), 0 2px 8px rgba(59,130,246,0.40) !important;
    transform: scale(1.12) !important;
}
[data-testid="stSlider"] [data-baseweb="slider"] [data-testid="stThumbValue"] {
    background: #2563EB !important;
    color: #FFFFFF !important;
    border-radius: 6px !important;
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    padding: 2px 7px !important;
}
[data-testid="stSlider"] label {
    font-size: 0.82rem !important;
    font-weight: 600 !important;
    color: #64748B !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    margin-bottom: 6px !important;
}

/* ── Info / success / warning / error boxes ── */
[data-testid="stAlert"] {
    border-radius: 10px !important;
    border-left-width: 4px !important;
    background: rgba(255,255,255,0.04) !important;
}

/* ── Dividers ── */
hr { border-color: rgba(255,255,255,0.08) !important; }

/* ── Headings ── */
h1 { font-size: 1.7rem !important; font-weight: 700 !important; color: #F1F5F9 !important; }
h2 { font-size: 1.25rem !important; font-weight: 600 !important; color: #CBD5E1 !important; }
h3 { font-size: 1.05rem !important; font-weight: 600 !important; color: #CBD5E1 !important; }

/* ── Container borders (st.container with border=True) ── */
[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 14px !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    background: #161B27 !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3) !important;
    padding: 4px 4px !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    border-radius: 10px !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    background: #161B27 !important;
}
[data-testid="stExpander"] summary { color: #CBD5E1 !important; }

/* ── Dataframe / data editor ── */
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {
    border-radius: 12px !important;
    overflow: hidden;
    border: 1px solid rgba(255,255,255,0.08) !important;
}

/* ── Code blocks ── */
[data-testid="stCodeBlock"] pre,
code {
    background: #0A0F1E !important;
    color: #7DD3FC !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 8px !important;
}

/* ── Checkbox ── */
[data-testid="stCheckbox"] label { color: #CBD5E1 !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #0D1117; border-radius: 10px; }
::-webkit-scrollbar-thumb { background: #2D3748; border-radius: 10px; }
::-webkit-scrollbar-thumb:hover { background: #4A5568; }

/* ── Top navbar / toolbar ── */
[data-testid="stHeader"] {
    background: #0D1117 !important;
    border-bottom: 1px solid rgba(255,255,255,0.07) !important;
}
/* Deploy button */
[data-testid="stAppDeployButton"] button,
[data-testid="stToolbarActionButton"],
[data-testid="stBaseButton-headerNoPadding"] {
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(255,255,255,0.14) !important;
    color: #CBD5E1 !important;
    border-radius: 8px !important;
}
[data-testid="stAppDeployButton"] button:hover,
[data-testid="stToolbarActionButton"]:hover,
[data-testid="stBaseButton-headerNoPadding"]:hover {
    background: rgba(255,255,255,0.13) !important;
    color: #FFFFFF !important;
}
/* Three-dot menu icon and any SVG icons in the toolbar */
[data-testid="stHeader"] svg,
[data-testid="stHeader"] button svg {
    fill: #94A3B8 !important;
    color: #94A3B8 !important;
}
[data-testid="stHeader"] button:hover svg {
    fill: #FFFFFF !important;
    color: #FFFFFF !important;
}
/* Toolbar text (e.g. "Deploy") */
[data-testid="stHeader"] button span,
[data-testid="stHeader"] button p {
    color: #CBD5E1 !important;
}
</style>
""", unsafe_allow_html=True)


def page_header(icon: str, title: str, subtitle: str = ""):
    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#1E3A5F 0%,#2563EB 100%);
                border-radius:16px; padding:24px 28px; margin-bottom:24px;
                box-shadow:0 4px 20px rgba(37,99,235,0.25);">
        <div style="font-size:1.6rem; font-weight:700; color:#FFFFFF; letter-spacing:-0.5px;">
            {icon} &nbsp;{title}
        </div>
        {"<div style='font-size:0.85rem;color:rgba(255,255,255,0.75);margin-top:5px;'>"+subtitle+"</div>" if subtitle else ""}
    </div>
    """, unsafe_allow_html=True)


def section_header(title: str):
    st.markdown(f"""
    <div style="font-size:0.7rem;font-weight:600;color:#475569;text-transform:uppercase;
                letter-spacing:0.08em;margin:20px 0 10px 0;padding-bottom:6px;
                border-bottom:2px solid rgba(255,255,255,0.08);">
        {title}
    </div>
    """, unsafe_allow_html=True)


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding:18px 4px 8px 4px; text-align:center;">
        <div style="font-size:2.2rem; margin-bottom:4px;">💼</div>
        <div style="font-size:1.25rem; font-weight:700; color:#FFFFFF; letter-spacing:-0.3px;">JobAgent</div>
        <div style="font-size:0.72rem; color:#94A3B8; margin-top:2px; letter-spacing:0.05em;">
            AI-POWERED JOB SEARCH
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    profile = get_latest_resume_profile()
    if profile:
        p = profile["parsed_profile"]
        st.markdown(f"""
        <div style="background:rgba(255,255,255,0.08); border-radius:10px; padding:12px 14px; margin-bottom:4px;">
            <div style="font-size:0.7rem; color:#94A3B8; text-transform:uppercase; letter-spacing:0.06em; margin-bottom:4px;">Active Resume</div>
            <div style="font-size:0.88rem; font-weight:600; color:#FFFFFF; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">⭐ {profile['filename']}</div>
            <div style="font-size:0.75rem; color:#CBD5E1; margin-top:4px;">{p.get('current_title','—')}</div>
            <div style="font-size:0.72rem; color:#64748B; margin-top:2px;">{', '.join(p.get('job_titles',[])[:2])}</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="background:rgba(251,191,36,0.15); border:1px solid rgba(251,191,36,0.3); border-radius:10px; padding:12px 14px; color:#FDE68A; font-size:0.82rem;">
            ⚠️ Upload your resume to start
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    stats   = get_today_stats(TODAY)
    total   = stats.get("total",   0) or 0
    applied = stats.get("applied", 0) or 0
    pending = max(total - applied, 0)
    avg_sc  = stats.get("avg_score") or 0

    st.markdown("""
    <div style="font-size:0.7rem; color:#94A3B8; text-transform:uppercase; letter-spacing:0.06em; margin-bottom:10px;">
        Today — """ + TODAY + """
    </div>
    """, unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    c1.metric("Found",     total)
    c2.metric("Applied",   applied)
    c1.metric("Pending",   pending)
    c2.metric("Avg Match", f"{avg_sc:.0%}")

    st.markdown("<div style='margin-top:10px'></div>", unsafe_allow_html=True)
    if st.button("🔄 Reset Today's Stats", use_container_width=True):
        reset_today_statuses(TODAY)
        st.rerun()

    st.divider()
    st.markdown(f"""
    <div style="font-size:0.72rem; color:#64748B; text-align:center; line-height:1.8;">
        ⏰ Runs daily at <strong style="color:#94A3B8;">{DAILY_RUN_HOUR:02d}:{DAILY_RUN_MINUTE:02d} AM ET</strong><br>
        <code style="background:rgba(255,255,255,0.08); color:#CBD5E1; padding:2px 6px; border-radius:4px; font-size:0.68rem;">python scheduler.py</code>
    </div>
    """, unsafe_allow_html=True)


# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_resume, tab_run, tab_today, tab_all, tab_excel, tab_settings = st.tabs([
    "📄 Resume",
    "🔍 Search Jobs",
    "📋 Today's Jobs",
    "✅ My Applications",
    "📥 Download Report",
    "⚙️ Settings",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Upload Resume
# ══════════════════════════════════════════════════════════════════════════════
with tab_resume:
    page_header("📄", "Resume", "The agent uses the ⭐ Primary resume to search jobs and score relevance.")

    # ── Upload ─────────────────────────────────────────────────────────────────
    with st.expander("Upload a new resume", expanded=not bool(get_all_resume_profiles())):
        uploaded = st.file_uploader("Drop PDF or DOCX", type=["pdf", "docx"])
        if uploaded:
            if st.button("Parse & Save Resume", type="primary", use_container_width=True):
                with st.spinner("Reading resume with AI..."):
                    try:
                        file_bytes = uploaded.read()
                        raw_text, parsed = parse_resume(uploaded.name, file_bytes)
                        (Path(UPLOADS_DIR) / uploaded.name).write_bytes(file_bytes)
                        new_id = save_resume_profile(uploaded.name, raw_text, parsed)

                        # Auto-set as primary if it's the only one
                        if len(get_all_resume_profiles()) == 1:
                            set_primary_resume(new_id)

                        st.success("Resume saved and parsed!")
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            st.metric("Experience", f"{parsed.get('years_of_experience','?')} yrs")
                            st.write("**Searching for:**")
                            for t in parsed.get("job_titles", [])[:5]:
                                st.write(f"• {t}")
                        with c2:
                            st.write("**Technical Skills**")
                            st.write(", ".join(parsed.get("skills",{}).get("technical",[])[:12]))
                        with c3:
                            st.write("**Industries**")
                            for i in parsed.get("industries", [])[:4]:
                                st.write(f"• {i}")
                            for e in parsed.get("education", [])[:2]:
                                st.write(f"• {e.get('degree','')} — {e.get('school','')}")
                        if parsed.get("summary"):
                            st.info(parsed["summary"])
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to parse resume: {e}")

    st.divider()

    # ── Saved resumes ──────────────────────────────────────────────────────────
    profiles = get_all_resume_profiles()
    if not profiles:
        st.info("No resumes yet — upload one above.")
    else:
        section_header("Saved Resumes  ·  ⭐ = Primary used for job searching")

        # Confirmation state for delete
        if "confirm_delete" not in st.session_state:
            st.session_state.confirm_delete = None

        for p in profiles:
            is_primary = bool(p.get("is_primary", 0))
            file_path  = Path(UPLOADS_DIR) / p["filename"]

            with st.container(border=True):
                col_info, col_star, col_dl, col_del = st.columns([5, 1.6, 1.4, 1.4])

                with col_info:
                    label = f"⭐ **{p['filename']}**" if is_primary else f"📄 {p['filename']}"
                    st.markdown(label)
                    uploaded_at = p["created_at"][:16].replace("T", " at ")
                    st.caption(f"Uploaded {uploaded_at}{'  ·  PRIMARY' if is_primary else ''}")

                with col_star:
                    if is_primary:
                        st.success("⭐ Primary", icon=None)
                    else:
                        if st.button(
                            "⭐ Set Primary",
                            key=f"star_{p['id']}",
                            use_container_width=True,
                            help="Agent will use this resume for all future searches",
                        ):
                            set_primary_resume(p["id"])
                            st.rerun()

                with col_dl:
                    if file_path.exists():
                        mime = "application/pdf" if p["filename"].endswith(".pdf") else \
                               "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        with open(file_path, "rb") as f:
                            st.download_button(
                                "⬇ Download",
                                f.read(),
                                p["filename"],
                                mime,
                                key=f"dl_{p['id']}",
                                use_container_width=True,
                            )
                    else:
                        st.caption("File not found")

                with col_del:
                    if is_primary:
                        st.caption("Primary — cannot delete")
                    elif st.session_state.confirm_delete == p["id"]:
                        # Confirm row
                        st.warning("Delete?")
                        cc1, cc2 = st.columns(2)
                        if cc1.button("Yes", key=f"yes_{p['id']}", use_container_width=True, type="primary"):
                            delete_resume_profile(p["id"])
                            if file_path.exists():
                                file_path.unlink()
                            st.session_state.confirm_delete = None
                            st.rerun()
                        if cc2.button("No", key=f"no_{p['id']}", use_container_width=True):
                            st.session_state.confirm_delete = None
                            st.rerun()
                    else:
                        if st.button(
                            "🗑 Delete",
                            key=f"del_{p['id']}",
                            use_container_width=True,
                        ):
                            st.session_state.confirm_delete = p["id"]
                            st.rerun()

        # ── Active resume preview ──────────────────────────────────────────────
        active = get_latest_resume_profile()
        if active:
            st.divider()
            section_header("Active Resume Details")
            parsed = active["parsed_profile"]
            d1, d2, d3 = st.columns(3)
            with d1:
                st.metric("Experience", f"{parsed.get('years_of_experience','?')} yrs")
                st.write("**Targeting roles:**")
                for t in parsed.get("job_titles", [])[:5]:
                    st.write(f"• {t}")
            with d2:
                st.write("**Technical Skills**")
                st.write(", ".join(parsed.get("skills",{}).get("technical",[])[:12]))
            with d3:
                st.write("**Industries**")
                for i in parsed.get("industries", [])[:4]:
                    st.write(f"• {i}")
            if parsed.get("summary"):
                st.info(parsed["summary"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Search Jobs
# ══════════════════════════════════════════════════════════════════════════════
with tab_run:
    page_header("🔍", "Search Jobs", "The agent runs automatically every day at 6:00 AM — or trigger a manual search anytime.")

    profile = get_latest_resume_profile()
    if not profile:
        st.error("Upload your resume first (Resume tab).")
    else:
        p = profile["parsed_profile"]
        st.info(
            f"Searching as: **{p.get('current_title','—')}**  \n"
            f"Target roles: {', '.join(p.get('job_titles',[])[:4])}"
        )

        if st.button("🔍 Search & Score Jobs Now", type="primary", use_container_width=True):
            prog   = st.progress(0)
            status = st.empty()
            try:
                from job_searcher import search_and_store_jobs, score_jobs
                status.info("Searching LinkedIn, Indeed, Greenhouse, Glassdoor, Dice, Monster…")
                prog.progress(30)
                n = search_and_store_jobs(p)
                status.info(f"Found **{n}** new jobs — scoring with AI…")
                prog.progress(70)
                s = score_jobs(p, TODAY)
                prog.progress(100)
                status.success(
                    f"Done! Found **{n}** new jobs, scored **{s}**. "
                    "Open **Today's Jobs** tab to review and mark which ones you applied to."
                )
                st.rerun()
            except Exception as e:
                status.error(f"Error: {e}")

        st.divider()
        section_header("Automatic Daily Schedule")
        st.markdown(
            "The scheduler runs the search every morning at **6:00 AM** automatically.  \n"
            "Start it once in a separate terminal and leave it running:"
        )
        st.code("python scheduler.py", language="bash")
        st.caption("Keep this terminal open. It will run the search every morning and save the reports to your Desktop.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Today's Jobs
# ══════════════════════════════════════════════════════════════════════════════
with tab_today:
    page_header("📋", f"Today's Jobs — {TODAY}", "Review jobs found today. Tick Applied?, enter the resume filename, and click Save Changes.")

    all_jobs   = get_all_jobs(limit=2000)
    today_jobs = [j for j in all_jobs if j.get("date") == TODAY]

    if not today_jobs:
        st.info("No jobs yet — go to **Search Jobs** tab and run a search.")
    else:
        # ── Stats row ──────────────────────────────────────────────────────────
        src_counts = {}
        for j in today_jobs:
            src_counts[j.get("source","?")] = src_counts.get(j.get("source","?"),0) + 1

        applied_today = sum(1 for j in today_jobs if j.get("manually_applied"))
        c1,c2,c3,c4,c5,c6,c7,c8 = st.columns(8)
        c1.metric("Total",       len(today_jobs))
        c2.metric("Applied",     applied_today)
        c3.metric("LinkedIn",    src_counts.get("LinkedIn",0))
        c4.metric("Indeed",      src_counts.get("Indeed",0))
        c5.metric("Greenhouse",  src_counts.get("Greenhouse",0))
        c6.metric("Glassdoor",   src_counts.get("Glassdoor",0))
        c7.metric("Dice",        src_counts.get("Dice",0))
        c8.metric("Monster",     src_counts.get("Monster",0))

        st.divider()

        # ── Filters ────────────────────────────────────────────────────────────
        fc1, fc2, fc3, fc4 = st.columns(4)
        with fc1:
            srcs    = ["All"] + sorted(set(j["source"] for j in today_jobs))
            sel_src = st.selectbox("Source", srcs, key="tj_src")
        with fc2:
            show_applied = st.selectbox("Applied?", ["All", "Not yet", "Already applied"], key="tj_app")
        with fc3:
            min_sc = st.slider("Min Match Score", 0.0, 1.0, 0.0, 0.05, key="tj_sc")
        with fc4:
            kw = st.text_input("Search title / company", key="tj_kw")

        filtered = today_jobs[:]
        if sel_src != "All":
            filtered = [j for j in filtered if j["source"] == sel_src]
        if min_sc > 0:
            filtered = [j for j in filtered if (j.get("relevance_score") or 0) >= min_sc]
        if kw:
            filtered = [j for j in filtered
                        if kw.lower() in j["title"].lower() or kw.lower() in j["company"].lower()]
        if show_applied == "Not yet":
            filtered = [j for j in filtered if not j.get("manually_applied")]
        elif show_applied == "Already applied":
            filtered = [j for j in filtered if j.get("manually_applied")]

        filtered.sort(key=lambda j: j.get("relevance_score") or -1, reverse=True)
        st.caption(f"Showing {len(filtered)} of {len(today_jobs)} jobs")

        # ── Job cards (page scrolls naturally — no inner scroll box) ─────────────
        if filtered:
            st.info(
                "After applying to a job on the company site, tick **✅ I Applied**, "
                "enter the resume filename you sent, then click **Save**.",
                icon="💡",
            )

            for job in filtered:
                jid      = job["job_id"]
                score    = job.get("relevance_score") or 0
                applied  = bool(job.get("manually_applied", 0))
                resume   = job.get("resume_filename") or ""

                # Score badge
                if score >= 0.80:
                    badge = f"🟢 {score:.0%}"
                elif score >= 0.65:
                    badge = f"🟡 {score:.0%}"
                elif score > 0:
                    badge = f"🔴 {score:.0%}"
                else:
                    badge = "⚪ —"

                with st.container(border=True):
                    top_left, top_right = st.columns([6, 2])

                    with top_left:
                        if score >= 0.80:
                            badge_html = f'<span style="background:#DCFCE7;color:#166534;padding:2px 9px;border-radius:20px;font-size:0.72rem;font-weight:600;">{score:.0%} Match</span>'
                        elif score >= 0.65:
                            badge_html = f'<span style="background:#FEF9C3;color:#854D0E;padding:2px 9px;border-radius:20px;font-size:0.72rem;font-weight:600;">{score:.0%} Match</span>'
                        elif score > 0:
                            badge_html = f'<span style="background:#FEE2E2;color:#991B1B;padding:2px 9px;border-radius:20px;font-size:0.72rem;font-weight:600;">{score:.0%} Match</span>'
                        else:
                            badge_html = '<span style="background:#F1F5F9;color:#64748B;padding:2px 9px;border-radius:20px;font-size:0.72rem;">Unscored</span>'

                        src_icon = {"LinkedIn":"🔵","Indeed":"🟣","Greenhouse":"🟢","Glassdoor":"🟠","Dice":"🎲","Monster":"🟥"}.get(job.get("source",""), "🔗")
                        applied_badge = ' &nbsp;<span style="background:#DCFCE7;color:#166534;padding:2px 8px;border-radius:20px;font-size:0.7rem;font-weight:600;">✅ Applied</span>' if applied else ""

                        st.markdown(f"""
                        <div style="margin-bottom:2px;">
                            <span style="font-size:1rem;font-weight:700;color:#0F172A;">{job['title']}</span>
                            <span style="color:#64748B;font-size:0.9rem;"> &nbsp;·&nbsp; {job['company']}</span>
                            {applied_badge}
                        </div>
                        <div style="font-size:0.78rem;color:#64748B;margin-top:3px;">
                            📍 {job.get('location','US')} &nbsp;·&nbsp;
                            {src_icon} {job['source']} &nbsp;·&nbsp;
                            💼 {(job.get('job_type') or '').title()} &nbsp;&nbsp;
                            {badge_html}
                        </div>
                        """, unsafe_allow_html=True)
                        if job.get("relevance_reason"):
                            st.caption(f"_{job['relevance_reason']}_")

                    with top_right:
                        st.link_button("🔗 Open Job", job["url"], use_container_width=True)

                    # Tracking form — uses a unique key per job so it never conflicts
                    with st.form(key=f"track_{jid}", border=False):
                        fc1, fc2, fc3 = st.columns([1, 3, 1])
                        with fc1:
                            new_applied = st.checkbox(
                                "✅ I Applied",
                                value=applied,
                                key=f"chk_{jid}",
                            )
                        with fc2:
                            new_resume = st.text_input(
                                "Resume saved as",
                                value=resume,
                                placeholder="e.g. Resume_DataEngineer_Google.pdf",
                                label_visibility="collapsed",
                                key=f"rfn_{jid}",
                            )
                        with fc3:
                            if st.form_submit_button("💾 Save", use_container_width=True):
                                if new_applied:
                                    mark_manually_applied(jid, new_resume)
                                else:
                                    unmark_manually_applied(jid)
                                st.rerun()

            # CSV download
            st.divider()
            csv_rows = [{
                "Date":    j.get("date",""),
                "Company": j.get("company",""),
                "Title":   j.get("title",""),
                "Location":j.get("location",""),
                "Source":  j.get("source",""),
                "Match":   f"{j.get('relevance_score',0):.0%}",
                "Applied": "Yes" if j.get("manually_applied") else "No",
                "Resume":  j.get("resume_filename",""),
                "URL":     j.get("url",""),
            } for j in filtered]
            st.download_button(
                "⬇ Download Today's Jobs CSV",
                pd.DataFrame(csv_rows).to_csv(index=False),
                f"jobs_{TODAY}.csv",
                "text/csv",
                use_container_width=True,
            )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — My Applications
# ══════════════════════════════════════════════════════════════════════════════
with tab_all:
    page_header("✅", "My Applications", "All positions you have manually applied to — company, role, link, and resume filename.")

    applied_jobs = get_manually_applied_jobs()

    if not applied_jobs:
        st.info(
            "No applications tracked yet.  \n"
            "Go to **Today's Jobs**, tick **Applied?** next to each job you applied to, "
            "enter the resume filename, and click **Save Changes**."
        )
    else:
        # ── Summary stats ──────────────────────────────────────────────────────
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Applied", len(applied_jobs))
        unique_companies = len(set(j["company"] for j in applied_jobs))
        m2.metric("Companies", unique_companies)
        unique_resumes = len(set(j.get("resume_filename","") for j in applied_jobs if j.get("resume_filename")))
        m3.metric("Resume Versions Used", unique_resumes)

        st.divider()

        # ── Filters ────────────────────────────────────────────────────────────
        fa1, fa2, fa3 = st.columns(3)
        with fa1:
            all_dates = ["All"] + sorted(set(j["date"] for j in applied_jobs), reverse=True)
            f_date = st.selectbox("Date", all_dates, key="app_date")
        with fa2:
            all_srcs = ["All"] + sorted(set(j["source"] for j in applied_jobs))
            f_src  = st.selectbox("Source", all_srcs, key="app_src")
        with fa3:
            f_kw = st.text_input("Search company / role", key="app_kw")

        filtered = applied_jobs[:]
        if f_date != "All": filtered = [j for j in filtered if j["date"]   == f_date]
        if f_src  != "All": filtered = [j for j in filtered if j["source"] == f_src]
        if f_kw:
            k = f_kw.lower()
            filtered = [j for j in filtered
                        if k in j["title"].lower() or k in j["company"].lower()]

        st.caption(f"Showing {len(filtered)} applications")

        # ── Tracking table ─────────────────────────────────────────────────────
        df = pd.DataFrame([{
            "Date Applied":    (j.get("applied_at") or j.get("date",""))[:10],
            "Company":         j.get("company",""),
            "Role Applied For": j.get("title",""),
            "Resume Saved As": j.get("resume_filename") or "—",
            "Source":          j.get("source",""),
            "Match":           round(j.get("relevance_score") or 0, 2),
            "Job Link":        j.get("url",""),
            "_job_id":         j.get("job_id",""),
        } for j in filtered])

        apps_height = min(38 + len(df) * 35, 1800)

        edited_apps = st.data_editor(
            df.drop(columns=["_job_id"]),
            column_config={
                "Date Applied":     st.column_config.TextColumn("Date Applied",     disabled=True),
                "Company":          st.column_config.TextColumn("Company",          disabled=True),
                "Role Applied For":  st.column_config.TextColumn("Role Applied For", disabled=True),
                "Resume Saved As":  st.column_config.TextColumn(
                    "Resume Saved As",
                    help="Update the resume filename if needed",
                    width="medium",
                ),
                "Source":   st.column_config.TextColumn("Source",  disabled=True),
                "Match":    st.column_config.ProgressColumn("Match", min_value=0, max_value=1, format="%.0%"),
                "Job Link": st.column_config.LinkColumn("Job Link"),
            },
            hide_index=True,
            use_container_width=True,
            height=apps_height,
            key="apps_editor",
        )

        col_save, col_dl = st.columns(2)
        with col_save:
            if st.button("💾 Update Resume Filenames", use_container_width=True):
                for i, row in edited_apps.iterrows():
                    job_id = df.iloc[i]["_job_id"]
                    mark_manually_applied(job_id, row["Resume Saved As"])
                st.success("Updated!")
                st.rerun()
        with col_dl:
            st.download_button(
                "⬇ Download CSV",
                edited_apps.to_csv(index=False),
                f"my_applications_{TODAY}.csv",
                "text/csv",
                use_container_width=True,
            )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — Excel / PDF Report
# ══════════════════════════════════════════════════════════════════════════════
with tab_excel:
    page_header("📥", "Download Report", "Color-coded report with all applications — available in Excel or PDF format.")

    st.markdown("""
    | Color | Meaning |
    |-------|---------|
    | 🟢 Green | Auto-applied successfully |
    | 🟡 Yellow | Needs you to apply manually |
    | 🔴 Red | Auto-apply failed |
    | ⬜ Grey | Skipped (low match score) |
    """)

    st.divider()

    # ── Generate buttons ───────────────────────────────────────────────────────
    col_xl, col_pdf = st.columns(2)

    with col_xl:
        section_header("Excel (.xlsx) — Workbook with filters & hyperlinks")
        if st.button("📊 Generate Excel Report", type="primary", use_container_width=True):
            with st.spinner("Building Excel report..."):
                try:
                    from excel_reporter import export_excel
                    path = export_excel(TODAY)
                    st.success(f"Saved to Desktop: `{Path(path).name}`")
                    with open(path, "rb") as f:
                        st.download_button(
                            "⬇ Download Excel",
                            f.read(),
                            Path(path).name,
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                            key="dl_xl_gen",
                        )
                except Exception as e:
                    st.error(f"Excel error: {e}")

        xl_today = Path.home() / "Desktop" / f"job_applications_{TODAY}.xlsx"
        if xl_today.exists():
            with open(xl_today, "rb") as f:
                st.download_button(
                    "⬇ Download Today's Excel",
                    f.read(),
                    xl_today.name,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    key="dl_xl_today",
                )

    with col_pdf:
        section_header("PDF (.pdf) — Printable landscape with stats banner")
        if st.button("📄 Generate PDF Report", type="primary", use_container_width=True):
            with st.spinner("Building PDF report..."):
                try:
                    from pdf_reporter import export_pdf
                    path = export_pdf(TODAY)
                    st.success(f"Saved to Desktop: `{Path(path).name}`")
                    with open(path, "rb") as f:
                        st.download_button(
                            "⬇ Download PDF",
                            f.read(),
                            Path(path).name,
                            "application/pdf",
                            use_container_width=True,
                            key="dl_pdf_gen",
                        )
                except Exception as e:
                    st.error(f"PDF error: {e}")

        pdf_today = Path.home() / "Desktop" / f"job_applications_{TODAY}.pdf"
        if pdf_today.exists():
            with open(pdf_today, "rb") as f:
                st.download_button(
                    "⬇ Download Today's PDF",
                    f.read(),
                    pdf_today.name,
                    "application/pdf",
                    use_container_width=True,
                    key="dl_pdf_today",
                )

    st.divider()

    # ── Previous reports ───────────────────────────────────────────────────────
    section_header("Previous Reports")
    desktop = Path.home() / "Desktop"
    xl_reports  = sorted(desktop.glob("job_applications_*.xlsx"), reverse=True)
    pdf_reports = sorted(desktop.glob("job_applications_*.pdf"),  reverse=True)
    all_dates   = sorted(
        {r.stem.replace("job_applications_", "") for r in xl_reports + pdf_reports},
        reverse=True,
    )

    if all_dates:
        hdr_a, hdr_b, hdr_c = st.columns([3, 1, 1])
        hdr_a.markdown("**Date**")
        hdr_b.markdown("**Excel**")
        hdr_c.markdown("**PDF**")

        for d in all_dates[:10]:
            ca, cb, cc = st.columns([3, 1, 1])
            ca.write(d)
            xl_file = desktop / f"job_applications_{d}.xlsx"
            pdf_file = desktop / f"job_applications_{d}.pdf"
            if xl_file.exists():
                with open(xl_file, "rb") as f:
                    cb.download_button(
                        "⬇ xlsx", f.read(), xl_file.name,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"xl_{d}",
                    )
            else:
                cb.write("—")
            if pdf_file.exists():
                with open(pdf_file, "rb") as f:
                    cc.download_button(
                        "⬇ pdf", f.read(), pdf_file.name,
                        "application/pdf",
                        key=f"pdf_{d}",
                    )
            else:
                cc.write("—")
    else:
        st.caption("No reports yet — run the agent to generate one.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — Settings
# ══════════════════════════════════════════════════════════════════════════════
with tab_settings:
    page_header("⚙️", "Settings", "Configure job search preferences, contact info, and scheduler.")

    env_path    = Path(__file__).parent / ".env"
    env_content = env_path.read_text() if env_path.exists() else ""

    with st.form("settings_form"):
        section_header("Search &amp; Apply Settings")
        c1, c2 = st.columns(2)
        with c1:
            new_min   = st.slider("Min Relevance Score to Apply",
                                  0.0, 1.0, float(os.getenv("MIN_RELEVANCE_SCORE","0.65")), 0.05)
            new_max   = st.number_input("Max Jobs Per Run", 10, 500,
                                        int(os.getenv("MAX_JOBS_PER_RUN","50")), 10)
        with c2:
            new_hour  = st.number_input("Auto-run Hour (0–23 ET)", 0, 23,
                                        int(os.getenv("DAILY_RUN_HOUR","9")))
            new_types = st.multiselect("Job Types",
                                       ["fulltime","contract","remote"], default=JOB_TYPES)

        section_header("Your Contact Info")
        c3, c4 = st.columns(2)
        with c3:
            new_name  = st.text_input("Full Name",
                                      value=os.getenv("CANDIDATE_NAME",""))
            new_phone = st.text_input("Phone Number",
                                      value=os.getenv("CANDIDATE_PHONE",""))
            new_li    = st.text_input("LinkedIn URL",
                                      value=os.getenv("CANDIDATE_LINKEDIN",""))
        with c4:
            new_web   = st.text_input("Personal Website / Portfolio",
                                      value=os.getenv("CANDIDATE_WEBSITE",""))
            new_head  = st.selectbox("Run Browser",
                                     ["Headless (background)", "Visible (debug)"],
                                     index=0 if os.getenv("HEADLESS","true")=="true" else 1)

        section_header("Screening Question Defaults (answered by AI)")
        c_s1, c_s2 = st.columns(2)
        with c_s1:
            new_work_auth = st.selectbox(
                "Authorized to work in the US?",
                ["yes", "no"],
                index=0 if os.getenv("WORK_AUTHORIZED","yes") == "yes" else 1,
            )
            new_sponsorship = st.selectbox(
                "Require visa sponsorship?",
                ["no", "yes"],
                index=0 if os.getenv("REQUIRES_SPONSORSHIP","no") == "no" else 1,
            )
            new_relocate = st.selectbox(
                "Willing to relocate?",
                ["no", "yes"],
                index=0 if os.getenv("WILLING_TO_RELOCATE","no") == "no" else 1,
            )
        with c_s2:
            new_sal_min = st.number_input(
                "Salary Expectation — Min ($)", 0, 500000,
                int(os.getenv("SALARY_MIN","100000")), 5000,
            )
            new_sal_max = st.number_input(
                "Salary Expectation — Max ($)", 0, 500000,
                int(os.getenv("SALARY_MAX","150000")), 5000,
            )
            new_notice = st.text_input(
                "Notice Period / Can Start In",
                value=os.getenv("NOTICE_PERIOD","2 weeks"),
            )

        section_header("LinkedIn Credentials")
        c5, c6 = st.columns(2)
        with c5:
            new_li_email = st.text_input("LinkedIn Email",
                                         value=os.getenv("LINKEDIN_EMAIL",""),
                                         type="default")
        with c6:
            new_li_pass  = st.text_input("LinkedIn Password",
                                         value=os.getenv("LINKEDIN_PASSWORD",""),
                                         type="password")

        saved = st.form_submit_button("💾 Save Settings", type="primary")

    if saved:
        updates = {
            "MIN_RELEVANCE_SCORE":   str(new_min),
            "MAX_JOBS_PER_RUN":      str(new_max),
            "DAILY_RUN_HOUR":        str(new_hour),
            "JOB_TYPES":             ",".join(new_types),
            "CANDIDATE_NAME":        new_name,
            "CANDIDATE_PHONE":       new_phone,
            "CANDIDATE_LINKEDIN":    new_li,
            "CANDIDATE_WEBSITE":     new_web,
            "HEADLESS":              "true" if "Headless" in new_head else "false",
            "WORK_AUTHORIZED":       new_work_auth,
            "REQUIRES_SPONSORSHIP":  new_sponsorship,
            "WILLING_TO_RELOCATE":   new_relocate,
            "SALARY_MIN":            str(new_sal_min),
            "SALARY_MAX":            str(new_sal_max),
            "NOTICE_PERIOD":         new_notice,
            "LINKEDIN_EMAIL":        new_li_email,
            "LINKEDIN_PASSWORD":     new_li_pass,
        }
        lines = env_content.splitlines()
        written: set[str] = set()
        new_lines = []
        for line in lines:
            if "=" in line and not line.strip().startswith("#"):
                key = line.split("=")[0].strip()
                if key in updates:
                    new_lines.append(f"{key}={updates[key]}")
                    written.add(key)
                    continue
            new_lines.append(line)
        for k, v in updates.items():
            if k not in written:
                new_lines.append(f"{k}={v}")
        env_path.write_text("\n".join(new_lines) + "\n")
        st.success("Settings saved — restart the app for changes to take effect.")

    st.divider()
    section_header("Scheduler")
    st.caption("Start this in a separate terminal — it runs the agent automatically every day:")
    st.code("python scheduler.py", language="bash")

    section_header("Manual Run (Terminal)")
    st.code("python daily_runner.py --run-now", language="bash")
    st.code("python daily_runner.py --run-now --skip-apply", language="bash")
