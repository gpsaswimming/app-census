"""GPSA Census — read-only analytics dashboard (the read side of app-census).

Reads the DOB-free Postgres store built by the ingest service. No writes: this
is a locked decision in the migration plan. Division assignments and City Meet
standards are seeded from version-controlled CSVs by ``scripts/`` importers.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the repo root importable (so `db`, `leagues`, and `dashboard.*` resolve)
# whether run via `streamlit run dashboard/app.py` or inside the container.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

from dashboard.analysis.alignment import render_alignment_analysis  # noqa: E402
from dashboard.analysis.division_setup import render_division_setup  # noqa: E402
from dashboard.analysis.overview import render_overview  # noqa: E402
from dashboard.analysis.qt_analysis import render_qt_analysis  # noqa: E402
from dashboard.analysis.team_analytics import render_team_analytics  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from db.config import DATABASE_URL  # noqa: E402
from db.models import Meet  # noqa: E402

st.set_page_config(
    page_title="GPSA Census",
    page_icon="🏊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
    .main-header { font-size: 2.5rem; font-weight: 700; color: #002366;
                   text-align: center; margin-bottom: 1rem; }
    [data-theme="dark"] .main-header { color: #6b9fff; }
    .sub-header { font-size: 1.2rem; color: #666; text-align: center;
                  margin-bottom: 2rem; }
    [data-theme="dark"] .sub-header { color: #aaa; }
    .stMetric { padding: 1rem; border-radius: 0.5rem;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_resource
def _engine():
    """Cached read-only engine, pinned to AUTOCOMMIT.

    The dashboard is read-only, but a plain session auto-opens a transaction on
    the first SELECT and holds it until commit/rollback. Under Streamlit's
    rerun-per-interaction model that transaction can sit open indefinitely —
    which (a) freezes the connection's data snapshot so freshly ingested meets
    never appear, and (b) holds locks that block schema migrations/DDL (ingest
    migrates on startup). AUTOCOMMIT makes every SELECT self-contained: no open
    transaction, always-fresh reads, no lingering locks.
    """
    return create_engine(DATABASE_URL, isolation_level="AUTOCOMMIT", future=True)


def _has_data(session) -> bool:
    return session.query(Meet.id).filter(Meet.date.isnot(None)).first() is not None


def main() -> None:
    st.markdown('<h1 class="main-header">🏊 GPSA Census Analytics</h1>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sub-header">Greater Peninsula Swimming Association | Season Analytics Dashboard</p>',
        unsafe_allow_html=True,
    )

    # Fresh session per rerun, closed at the end — with the AUTOCOMMIT engine this
    # leaves no transaction or lock behind.
    session = Session(_engine())
    try:
        if not _has_data(session):
            st.warning("⚠️ No meet data found. Ingest meets through the ingest service first.")
            st.info("The dashboard reads the Postgres store populated by `POST /commit`.")
            return

        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📈 Overview",
            "⚖️ Alignment Analysis",
            "🏆 Team Analytics",
            "🎯 Qualifying Time Analysis",
            "⚙️ Division Setup",
        ])

        with tab1:
            render_overview(session)
        with tab2:
            render_alignment_analysis(session)
        with tab3:
            render_team_analytics(session)
        with tab4:
            render_qt_analysis(session)
        with tab5:
            render_division_setup(session)
    finally:
        session.close()


if __name__ == "__main__":
    main()
