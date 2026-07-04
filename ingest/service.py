"""Ingest pipeline: validate → preview → idempotent commit.

Flow (per the migration plan):
  raw bytes → swimparse (DOB-free, scored) → validate → {preview | commit}
  commit = idempotent upsert keyed on meet_key + an import_log audit row.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from db.loader import insert_meet, meet_key_for
from db.models import ImportLog, Meet
from ingest.swimparse_runner import SwimparseError, parse_bytes


class IngestError(ValueError):
    """A parsed meet failed validation and must not be stored."""


def _team_scores(meet: dict) -> dict[str, float]:
    scores: dict[str, float] = {t["code"]: 0.0 for t in meet.get("teams", [])}
    for ev in meet.get("events", []):
        for r in ev.get("results", []):
            code = r.get("teamCode")
            if code in scores:
                scores[code] += r.get("points") or 0.0
    return scores


def _num_results(meet: dict) -> int:
    return sum(len(ev.get("results", [])) for ev in meet.get("events", []))


def validate(meet: dict) -> None:
    """Correctness gate. Reject anything that would poison the store."""
    if meet.get("format") not in ("sdif-v3", "hy3"):
        raise IngestError(f"unrecognized format: {meet.get('format')!r}")
    if not meet.get("ageProfile"):
        raise IngestError("meet is not DOB-free (no ageProfile) — refusing to store")
    if not meet.get("teams"):
        raise IngestError("no teams in file")
    if _num_results(meet) == 0:
        raise IngestError("no results in file")
    if not (meet.get("meet") or {}).get("startDate"):
        raise IngestError("meet has no date — cannot derive season or meet_key")


def _summary(meet: dict) -> dict:
    info = meet.get("meet") or {}
    return {
        "meet_key": meet_key_for(meet),
        "name": info.get("name"),
        "date": info.get("startDate"),
        "season": int(info["startDate"][:4]) if info.get("startDate") else None,
        "format": meet.get("format"),
        "ageProfile": meet.get("ageProfile"),
        "teams": [t["code"] for t in meet.get("teams", [])],
        "teamScores": _team_scores(meet),
        "numEvents": len(meet.get("events", [])),
        "numResults": _num_results(meet),
        "numSwimmers": len(meet.get("swimmers", [])),
    }


def preview(data: bytes, filename: str) -> dict:
    """Parse + validate only. No DB write. Returns a summary for review."""
    meet = parse_bytes(data, filename)
    validate(meet)
    return _summary(meet)


def commit(session: Session, data: bytes, filename: str, *, imported_by: str | None = None) -> dict:
    """Parse + validate + idempotently upsert. Writes an import_log row.

    Idempotent on ``meet_key``: a re-upload of the same meet replaces its events/
    results/relays (delete-then-insert) rather than double-counting. Season
    athletes are get-or-created, so they survive the replace.
    """
    meet = parse_bytes(data, filename)
    validate(meet)
    key = meet_key_for(meet)

    existing = session.query(Meet).filter_by(meet_key=key).one_or_none()
    replaced = existing is not None
    if existing is not None:
        session.delete(existing)  # cascades events → results / relays / meet_teams
        session.flush()

    m = insert_meet(session, meet, imported_by=imported_by)

    summary = _summary(meet)
    session.add(
        ImportLog(
            meet_key=key,
            meet_id=m.id,
            source_filename=filename,
            fmt=meet.get("format"),
            age_profile=meet.get("ageProfile"),
            status="committed",
            message="updated" if replaced else "created",
            num_events=summary["numEvents"],
            num_results=summary["numResults"],
            team_scores=summary["teamScores"],
            imported_by=imported_by,
        )
    )
    session.commit()

    return {"status": "updated" if replaced else "created", "meet_id": m.id, **summary}


__all__ = ["IngestError", "SwimparseError", "preview", "commit", "validate"]
