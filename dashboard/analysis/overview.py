"""Database Overview tab.

Renders top-level metrics and summary charts for the selected season(s):
athlete count, meet count, event count, total swims, swimmers-by-team
bar chart, and meets-by-month donut chart.
"""
import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import func, or_

from db.models import Event, Meet, Result, Team


def render_overview(session) -> None:
    """Render the Database Overview tab."""
    st.header("Database Overview")

    all_seasons = sorted(
        {m.date[:4] for m in session.query(Meet.date).filter(Meet.date.isnot(None)).all() if m.date},
        reverse=True,
    )
    seasons = st.multiselect("Season(s)", options=all_seasons, default=all_seasons, key="overview_seasons")
    st.markdown("---")

    season_dates = [m.date for m in session.query(Meet).all() if m.date and m.date[:4] in seasons]
    season_filter = or_(*[Meet.date.like(f"{s}%") for s in seasons]) if seasons else True

    col1, col2, col3, col4 = st.columns(4)

    total_swimmers = session.query(func.count(func.distinct(Result.athlete_id))).select_from(Result).join(
        Event, Result.event_id == Event.id
    ).join(Meet, Event.meet_id == Meet.id).filter(
        Meet.date.isnot(None), season_filter
    ).scalar() or 0
    with col1:
        st.metric("Total Swimmers", f"{total_swimmers:,}")

    total_meets = session.query(func.count(func.distinct(Meet.id))).filter(
        Meet.date.in_(season_dates)
    ).scalar() or 0
    with col2:
        st.metric("Total Meets", total_meets)

    total_events = session.query(func.count(Event.id)).select_from(Event).join(
        Meet, Event.meet_id == Meet.id
    ).filter(Meet.date.in_(season_dates)).scalar() or 0
    with col3:
        st.metric("Total Events", f"{total_events:,}")

    total_swims = session.query(func.count(Result.id)).select_from(Result).join(
        Event, Result.event_id == Event.id
    ).join(Meet, Event.meet_id == Meet.id).filter(
        Meet.date.isnot(None), season_filter
    ).scalar() or 0
    with col4:
        st.metric("Total Swims", f"{total_swims:,}")

    col1, col2 = st.columns(2)
    with col1:
        _chart_swimmers_by_team(session, seasons)
    with col2:
        _chart_meets_by_month(session, seasons)


def _chart_swimmers_by_team(session, seasons) -> None:
    st.subheader("Swimmers by Team")

    data = session.query(
        Team.name,
        func.count(func.distinct(Result.athlete_id)).label("swimmers"),
    ).select_from(Team).join(
        Result, Team.id == Result.team_id
    ).join(
        Event, Result.event_id == Event.id
    ).join(
        Meet, Event.meet_id == Meet.id
    ).filter(
        or_(*[Meet.date.like(f"{s}%") for s in seasons]) if seasons else True
    ).group_by(Team.name).order_by(func.count(func.distinct(Result.athlete_id)).desc()).all()

    if data:
        df = pd.DataFrame(data, columns=["Team", "Swimmers"])
        fig = px.bar(df, x="Team", y="Swimmers", color="Swimmers", color_continuous_scale="Viridis")
        fig.update_layout(showlegend=False, height=400)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data available")


def _chart_meets_by_month(session, seasons) -> None:
    st.subheader("Meets by Month")

    meets = session.query(Meet).filter(
        Meet.date.isnot(None),
        or_(*[Meet.date.like(f"{s}%") for s in seasons]) if seasons else True,
    ).all()

    if meets:
        month_data: dict[str, int] = {}
        for meet in meets:
            if meet.date and len(meet.date) >= 7:
                month = meet.date[5:7]
                month_name = {"06": "June", "07": "July", "08": "August"}.get(month, month)
                month_data[month_name] = month_data.get(month_name, 0) + 1

        df = pd.DataFrame(list(month_data.items()), columns=["Month", "Meets"])
        fig = px.pie(df, values="Meets", names="Month", hole=0.4)
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data available")
