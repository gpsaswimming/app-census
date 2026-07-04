"""Minimal NormalizedMeet → ORM loader.

Phase 2 scope only: enough to prove the schema round-trips a real (DOB-free)
swimparse fixture. It does a plain INSERT and relies on the `meet_key` unique
constraint to reject a duplicate. The **idempotent upsert**, the score() gate,
validation, and audit logging are Phase 3 (ingest) — this helper is the seam
they will build on or replace.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from db.models import (
    Athlete,
    Event,
    Meet,
    MeetTeam,
    RelayLeg,
    RelayResult,
    Result,
    Team,
)


def name_key(last: str | None, first: str | None) -> str:
    """Canonical cross-season name key: ``LAST|FIRST`` upper-cased."""
    return f"{(last or '').strip()}|{(first or '').strip()}".upper()


def meet_key_for(meet: dict) -> str:
    """Idempotency key: meet date + the sorted set of team codes.

    Stable across re-exports of the same meet and across SDIF/HY3 of it.
    """
    date = (meet.get("meet") or {}).get("startDate") or "unknown-date"
    codes = sorted(t["code"] for t in meet.get("teams", []))
    return f"{date}|{','.join(codes)}"


def _season_of(meet: dict) -> int | None:
    date = (meet.get("meet") or {}).get("startDate")
    return int(date[:4]) if date else None


def insert_meet(session: Session, meet: dict, *, imported_by: str | None = None) -> Meet:
    """Insert a DOB-free NormalizedMeet dict and return the persisted Meet.

    Raises if the meet lacks an ``ageProfile`` stamp — an un-league'd parse still
    carries DOB and must never reach the store.
    """
    if not meet.get("ageProfile"):
        raise ValueError(
            "refusing to load a NormalizedMeet with no ageProfile — parse it "
            "with a league profile so it is DOB-free"
        )

    info = meet.get("meet") or {}
    season = _season_of(meet)

    # Teams (get-or-create by canonical code).
    teams_by_code: dict[str, Team] = {}
    for t in meet.get("teams", []):
        team = session.query(Team).filter_by(code=t["code"]).one_or_none()
        if team is None:
            team = Team(code=t["code"], full_code=t.get("fullCode"), name=t.get("name"))
            session.add(team)
            session.flush()
        teams_by_code[t["code"]] = team

    host = None
    if info.get("hostName"):
        host = next((tm for tm in teams_by_code.values() if tm.name == info["hostName"]), None)

    m = Meet(
        meet_key=meet_key_for(meet),
        name=info.get("name"),
        date=info.get("startDate"),
        season=season,
        course=info.get("course"),
        fmt=meet.get("format"),
        age_profile=meet.get("ageProfile"),
        source_software=(meet.get("source") or {}).get("software"),
        host_team=host,
        imported_by=imported_by,
    )
    session.add(m)

    # Team scores = sum of individual + relay points per team.
    scores: dict[str, float] = {c: 0.0 for c in teams_by_code}

    # Athletes (season-scoped identity), keyed by swimparse's per-meet swimmer id.
    athletes_by_swid: dict[str, Athlete] = {}
    for s in meet.get("swimmers", []):
        team = teams_by_code.get(s.get("teamCode"))
        a = Athlete(
            season=season,
            name_key=name_key(s.get("lastName"), s.get("firstName")),
            last_name=s.get("lastName"),
            first_name=s.get("firstName"),
            full_name=s.get("fullName"),
            gender=s.get("gender"),
            age_group=s.get("ageGroup"),
            team=team,
        )
        session.add(a)
        athletes_by_swid[s["id"]] = a

    for ev in meet.get("events", []):
        ag = ev.get("ageGroup") or {}
        event = Event(
            meet=m,
            event_number=ev.get("number") or None,
            event_type=ev.get("type"),
            gender=ev.get("gender"),
            age_group=ag.get("label"),
            age_group_lower=ag.get("lower"),
            age_group_upper=ag.get("upper"),
            distance=ev.get("distance"),
            stroke=ev.get("stroke"),
            description=ev.get("description"),
        )
        session.add(event)

        for r in ev.get("results", []):
            team = teams_by_code.get(r.get("teamCode"))
            pts = r.get("points") or 0.0
            if r.get("teamCode") in scores:
                scores[r["teamCode"]] += pts
            final = r.get("finalTime") or {}
            seed = r.get("seedTime") or {}

            if r.get("kind") == "relay":
                relay = RelayResult(
                    event=event,
                    team=team,
                    relay_letter=r.get("relayLetter"),
                    time_seconds=final.get("seconds"),
                    time_formatted=final.get("text"),
                    place=r.get("place"),
                    points=pts,
                    status=r.get("status"),
                    disqualified=bool(r.get("disqualified")),
                )
                session.add(relay)
                for leg in r.get("legs", []):
                    session.add(
                        RelayLeg(
                            relay_result=relay,
                            athlete=athletes_by_swid.get(leg.get("swimmerId")),
                            leg_order=leg.get("legOrder"),
                            swimmer_name=leg.get("name"),
                        )
                    )
            else:
                session.add(
                    Result(
                        event=event,
                        athlete=athletes_by_swid.get(r.get("swimmerId")),
                        team=team,
                        seed_seconds=seed.get("seconds"),
                        time_seconds=final.get("seconds"),
                        time_formatted=final.get("text"),
                        place=r.get("place"),
                        points=pts,
                        status=r.get("status"),
                        disqualified=bool(r.get("disqualified")),
                    )
                )

    for code, team in teams_by_code.items():
        session.add(MeetTeam(meet=m, team=team, score=scores.get(code, 0.0)))

    session.flush()
    return m
