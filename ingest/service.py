"""Ingest pipeline: validate → preview → idempotent commit.

Flow (per the migration plan):
  raw bytes → swimparse (DOB-free, scored) → validate → {preview | commit}
  commit = idempotent upsert keyed on meet_key + an import_log audit row.
"""

from __future__ import annotations

import io
import os
import zipfile

from sqlalchemy.orm import Session

from db.loader import insert_meet, meet_key_for
from db.models import ImportLog, Meet
from ingest.swimparse_runner import SwimparseError, parse_bytes


class IngestError(ValueError):
    """A parsed meet failed validation and must not be stored."""


# Meet types the analytics tabs recognize. Supplied by the caller (the folder
# signal the old census used is gone at the API boundary); None = unknown.
MEET_TYPES = ("dual", "invitational", "city_meet", "exhibition")

# Result-file extensions swimparse can parse (SDIF sometimes arrives as .txt).
# Preference order when a zip holds more than one.
_MEET_EXTS = (".sd3", ".hy3", ".txt")


def _extract_from_zip(data: bytes) -> tuple[bytes, str]:
    """Pull the meet-result file out of a zip export.

    Meet Maestro / Hy-Tek exports are usually zipped, so accept a `.zip` and
    unwrap it here. Picks the single `.sd3`/`.hy3`/`.txt` entry (preferring
    `.sd3`, then `.hy3`, then `.txt`), skipping directories and macOS resource
    forks. Returns the inner file's bytes + basename.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            cands = [
                n for n in zf.namelist()
                if not n.endswith("/")
                and not n.startswith("__MACOSX")
                and os.path.basename(n)
                and os.path.splitext(n)[1].lower() in _MEET_EXTS
            ]
            if not cands:
                raise IngestError("zip contains no .sd3/.hy3/.txt result file")
            order = {ext: i for i, ext in enumerate(_MEET_EXTS)}
            cands.sort(key=lambda n: (order[os.path.splitext(n)[1].lower()], n))
            pick = cands[0]
            return zf.read(pick), os.path.basename(pick)
    except zipfile.BadZipFile as exc:
        raise IngestError("upload is not a valid zip file") from exc


def unwrap_upload(data: bytes, filename: str) -> tuple[bytes, str]:
    """If the upload is a zip, return the meet file inside; else pass through.

    Detects a zip by its magic bytes (so a mis-named `.sd3` that is really a zip
    still works) or a `.zip` extension.
    """
    is_zip = data[:4] == b"PK\x03\x04" or (filename or "").lower().endswith(".zip")
    return _extract_from_zip(data) if is_zip else (data, filename)


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
    meet_data, meet_name = unwrap_upload(data, filename)
    meet = parse_bytes(meet_data, meet_name)
    validate(meet)
    return _summary(meet)


def commit(
    session: Session,
    data: bytes,
    filename: str,
    *,
    imported_by: str | None = None,
    meet_type: str | None = None,
) -> dict:
    """Parse + validate + idempotently upsert. Writes an import_log row.

    Idempotent on ``meet_key``: a re-upload of the same meet replaces its events/
    results/relays (delete-then-insert) rather than double-counting. Season
    athletes are get-or-created, so they survive the replace.

    ``meet_type`` (one of ``MEET_TYPES``) is optional metadata the caller
    supplies; the analytics tabs filter on it.
    """
    if meet_type is not None and meet_type not in MEET_TYPES:
        raise IngestError(f"unknown meet_type {meet_type!r}; expected one of {MEET_TYPES}")

    meet_data, meet_name = unwrap_upload(data, filename)
    meet = parse_bytes(meet_data, meet_name)
    validate(meet)
    key = meet_key_for(meet)

    existing = session.query(Meet).filter_by(meet_key=key).one_or_none()
    replaced = existing is not None
    if existing is not None:
        session.delete(existing)  # cascades events → results / relays / meet_teams
        session.flush()

    m = insert_meet(session, meet, imported_by=imported_by, meet_type=meet_type)

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
