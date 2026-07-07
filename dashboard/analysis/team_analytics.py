"""Team Analytics tab.

Renders team roster sizes, City Meet qualifier counts and rates,
summary metrics, and downloadable CSV.
"""
import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import and_, distinct, func, or_

from db.models import Athlete, CityMeetStandard, Event, Meet, Result, Team

_MEET_TYPE_MAP = {
    "Dual": "dual",
    "Invitational (SSI)": "invitational",
    "City Meet": "city_meet",
    "Exhibition": "exhibition",
}


def render_team_analytics(session) -> None:
    """Render the Team Analytics tab."""
    st.header("Team Analytics")

    all_seasons = sorted(
        {m.date[:4] for m in session.query(Meet.date).filter(Meet.date.isnot(None)).all() if m.date},
        reverse=True,
    )

    all_teams = sorted([t.name for t in session.query(Team).order_by(Team.name).all() if t.name])
    col1, col2, col3 = st.columns(3)
    with col1:
        seasons = st.multiselect("Season(s)", options=all_seasons, default=all_seasons, key="ta_seasons")
    with col2:
        selected_teams = st.multiselect("Filter Teams", all_teams, key="ta_teams")
    with col3:
        selected_labels = st.multiselect(
            "Meet Types", list(_MEET_TYPE_MAP.keys()),
            default=["Dual", "Invitational (SSI)"],
            key="ta_meet_types",
        )
    meet_types = [_MEET_TYPE_MAP[label] for label in selected_labels]

    if not seasons:
        st.warning("Please select at least one season.")
        return

    st.markdown("---")
    st.subheader("Team Size and City Meet Qualifiers")

    standards_count = session.query(CityMeetStandard).count()

    season_filter = or_(*[Meet.date.like(f"{s}%") for s in seasons])
    meet_type_filter = [Meet.meet_type.in_(meet_types)] if meet_types else []

    team_roster_data = session.query(
        Team.name.label("team_name"),
        func.count(distinct(Result.athlete_id)).label("roster_size"),
    ).select_from(Team).join(
        Result, Team.id == Result.team_id
    ).join(
        Event, Result.event_id == Event.id
    ).join(
        Meet, Event.meet_id == Meet.id
    ).filter(
        Meet.date.isnot(None), season_filter, *meet_type_filter
    ).group_by(Team.name).all()

    if not team_roster_data:
        st.info("No team data available for selected seasons.")
        return

    df_teams = pd.DataFrame(team_roster_data, columns=["Team", "Roster Size"])

    if standards_count > 0:
        all_qualifying = session.query(
            Team.name.label("team_name"),
            Athlete.id.label("swimmer_id"),
            Event.distance,
            Event.stroke,
            Result.time_seconds,
        ).select_from(Result).join(
            Event, Result.event_id == Event.id
        ).join(
            Athlete, Result.athlete_id == Athlete.id
        ).join(
            Team, Result.team_id == Team.id
        ).join(
            Meet, Event.meet_id == Meet.id
        ).join(
            CityMeetStandard,
            and_(
                CityMeetStandard.gender == Event.gender,
                CityMeetStandard.distance == Event.distance,
                CityMeetStandard.stroke == Event.stroke,
                # Match the swimmer's OWN age band (DOB-free replacement for the
                # old league_age.between): the swimmer's band must sit inside the
                # standard's age range, so swim-ups count toward their own bracket.
                CityMeetStandard.age_group_lower <= Athlete.age_group_lower,
                Athlete.age_group_upper <= CityMeetStandard.age_group_upper,
                # Judge each swim against the standards in effect for its season.
                CityMeetStandard.season_start <= Meet.season,
                CityMeetStandard.season_end >= Meet.season,
            ),
        ).filter(
            Result.time_seconds.isnot(None),
            Result.disqualified == False,  # noqa: E712
            Result.time_seconds <= CityMeetStandard.standard_seconds,
            Meet.date.isnot(None),
            season_filter,
            *meet_type_filter,
        ).all()

        if all_qualifying:
            df_qual = pd.DataFrame(all_qualifying, columns=[
                "Team", "swimmer_id", "Distance", "Stroke", "Time"
            ])
            df_qual = df_qual.loc[df_qual.groupby(["Team", "swimmer_id", "Distance", "Stroke"])["Time"].idxmin()]

            qualifiers_by_team = df_qual.groupby("Team").agg(
                {"swimmer_id": "nunique"}
            ).rename(columns={"swimmer_id": "Qualifiers"}).reset_index()

            cuts_by_team = df_qual.groupby("Team").size().reset_index(name="Total Cuts")

            df_teams = df_teams.merge(qualifiers_by_team, on="Team", how="left")
            df_teams = df_teams.merge(cuts_by_team, on="Team", how="left")
            df_teams["Qualifiers"] = df_teams["Qualifiers"].fillna(0).astype(int)
            df_teams["Total Cuts"] = df_teams["Total Cuts"].fillna(0).astype(int)
            df_teams["Qual %"] = (df_teams["Qualifiers"] / df_teams["Roster Size"] * 100).round(1)
            df_teams["Avg Cuts/Qualifier"] = (df_teams["Total Cuts"] / df_teams["Qualifiers"]).fillna(0).round(1)
        else:
            df_teams["Qualifiers"] = 0
            df_teams["Total Cuts"] = 0
            df_teams["Qual %"] = 0.0
            df_teams["Avg Cuts/Qualifier"] = 0.0
    else:
        st.info("ℹ️ City Meet standards not loaded. Run `python scripts/import_city_meet_standards.py` to enable qualifier tracking.")
        df_teams["Qualifiers"] = "N/A"
        df_teams["Total Cuts"] = "N/A"
        df_teams["Qual %"] = "N/A"

    if selected_teams:
        df_teams = df_teams[df_teams["Team"].isin(selected_teams)]

    df_teams = df_teams.sort_values("Roster Size", ascending=False)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Teams", len(df_teams))
    with col2:
        st.metric("Avg Roster Size", f"{df_teams['Roster Size'].mean():.0f}")
    if standards_count > 0:
        with col3:
            st.metric("Total Qualifiers", int(df_teams["Qualifiers"].sum()))
        with col4:
            st.metric("Avg Qual %", f"{df_teams['Qual %'].mean():.1f}%")

    st.dataframe(df_teams, hide_index=True, use_container_width=True, height=500)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Roster Size by Team")
        fig = px.bar(df_teams.head(15), x="Team", y="Roster Size",
                     color="Roster Size", color_continuous_scale="Blues",
                     title="Top 15 Teams by Roster Size")
        fig.update_xaxes(tickangle=45)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        if standards_count > 0:
            st.subheader("Qualification Rate by Team")
            fig = px.bar(df_teams.head(15), x="Team", y="Qual %",
                         color="Qual %", color_continuous_scale="Greens",
                         title="Top 15 Teams by Qualification %")
            fig.update_xaxes(tickangle=45)
            fig.update_yaxes(range=[0, 100])
            st.plotly_chart(fig, use_container_width=True)

    csv = df_teams.to_csv(index=False)
    st.download_button(
        label="📥 Download Team Analytics (CSV)",
        data=csv,
        file_name=f"team_analytics_{'_'.join(seasons)}.csv",
        mime="text/csv",
    )
