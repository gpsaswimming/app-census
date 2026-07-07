"""Division configuration reader.

The dashboard is a read-only view over Postgres (a locked decision in the
migration plan), so this manager exposes only reads. Division assignments are
edited through the version-controlled CSV importer
(``scripts/import_divisions.py``), not the UI.
"""
from __future__ import annotations

from typing import Dict, List

from sqlalchemy.orm import Session

from db.models import DivisionConfiguration, Meet, Team


class DivisionConfigManager:
    """Read division configurations for teams by season (read-only)."""

    def __init__(self, session: Session):
        self.session = session

    def get_divisions_for_season(self, season: int) -> Dict[str, List[dict]]:
        """Return all division assignments for a season.

        Returns a dict mapping division name → list of team dicts, plus an
        ``'unassigned'`` bucket:
            {'red': [{'id': 1, 'code': 'MBKM', 'name': '...'}], ..., 'unassigned': [...]}
        """
        configs = self.session.query(DivisionConfiguration).filter_by(season=season).all()

        divisions: Dict[str, List[dict]] = {"red": [], "white": [], "blue": [], "unassigned": []}
        assigned_team_ids = {c.team_id for c in configs}

        for config in configs:
            divisions[config.division].append(
                {"id": config.team.id, "code": config.team.code, "name": config.team.name}
            )

        for team in self.session.query(Team).all():
            if team.id not in assigned_team_ids:
                divisions["unassigned"].append(
                    {"id": team.id, "code": team.code, "name": team.name}
                )

        for teams in divisions.values():
            teams.sort(key=lambda t: t["code"] or "")

        return divisions

    def get_available_seasons(self) -> List[int]:
        """Return all seasons that have meets, sorted descending."""
        rows = (
            self.session.query(Meet.season)
            .filter(Meet.season.isnot(None))
            .distinct()
            .order_by(Meet.season.desc())
            .all()
        )
        return [r[0] for r in rows]
