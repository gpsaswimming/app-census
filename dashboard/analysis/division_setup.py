"""Division Setup tab (read-only).

Shows the Red/White/Blue division assignments for a season. The dashboard is a
read-only reader over Postgres (a locked decision in the migration plan), so
assignments are *edited* through the version-controlled CSV importer
(``scripts/import_divisions.py``), not here.
"""
import streamlit as st

from dashboard.utils.division_config import DivisionConfigManager


def render_division_setup(session) -> None:
    """Render the (read-only) Division Configuration tab."""
    st.header("Division Configuration")
    st.markdown(
        "Red / White / Blue assignments by season. This view is **read-only** — "
        "edit assignments in `division_configs/divisions.csv` and re-run "
        "`python scripts/import_divisions.py`."
    )

    division_manager = DivisionConfigManager(session)
    available_seasons = division_manager.get_available_seasons()

    if not available_seasons:
        st.warning("No seasons found in database.")
        return

    selected_season = st.selectbox(
        "Select Season", options=available_seasons, format_func=str
    )

    st.subheader(f"Division Assignments for {selected_season}")

    divisions = division_manager.get_divisions_for_season(selected_season)

    col1, col2, col3, col4 = st.columns(4)
    for col, key, title in (
        (col1, "red", "### 🔴 Red Division"),
        (col2, "white", "### ⚪ White Division"),
        (col3, "blue", "### 🔵 Blue Division"),
        (col4, "unassigned", "### ⚫ Unassigned"),
    ):
        with col:
            st.markdown(title)
            for team in divisions[key]:
                st.markdown(f"**{team['code']}**")
                st.caption(team["name"] or "")

    st.markdown("---")
    st.subheader("Summary")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Red", len(divisions["red"]))
    with col2:
        st.metric("White", len(divisions["white"]))
    with col3:
        st.metric("Blue", len(divisions["blue"]))
    with col4:
        st.metric("Unassigned", len(divisions["unassigned"]))
