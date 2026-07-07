"""Query filter builder for the GPSA dashboard.

Shared utility used by multiple analysis tabs to translate sidebar
selections into SQLAlchemy filter expressions.
"""
from __future__ import annotations

from sqlalchemy import or_

from db.models import Event, Meet, Result, Team


def build_filters(session, seasons, teams, age_groups, gender, meet_types=None):
    """Build a SQLAlchemy filter list from sidebar selections.

    Args:
        session: SQLAlchemy session.
        seasons: List of season year strings (e.g. ['2024', '2025']).
        teams: List of team name strings (empty = all).
        age_groups: List of event age-group strings (empty = all).
        gender: 'All', 'Boys', or 'Girls'.
        meet_types: Optional list of meet type strings (empty = all).

    Returns:
        List of SQLAlchemy filter expressions suitable for ``.filter(*filters)``.
    """
    filters = []

    if seasons:
        filters.append(or_(*[Meet.date.like(f"{s}%") for s in seasons]))

    if meet_types:
        filters.append(Meet.meet_type.in_(meet_types))

    if teams:
        team_ids = [t.id for t in session.query(Team).filter(Team.name.in_(teams)).all()]
        filters.append(Result.team_id.in_(team_ids))

    if gender != "All":
        gender_code = "M" if gender == "Boys" else "F"
        filters.append(Event.gender == gender_code)

    if age_groups:
        age_filters = [Event.age_group == ag for ag in age_groups]
        if age_filters:
            filters.append(or_(*age_filters))

    return filters
