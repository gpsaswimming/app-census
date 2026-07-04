"""Schema round-trip + guardrails.

Runs against in-memory SQLite (no Docker) using the same `Base.metadata` the
Alembic baseline creates. Loads the real DOB-free swimparse fixture, so it also
proves the loader maps a NormalizedMeet correctly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.loader import insert_meet, meet_key_for
from db.models import Athlete, Base, Event, Meet, MeetTeam, RelayResult, Result

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "gg-at-ww.census.json"


@pytest.fixture()
def meet_json() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_no_dob_columns_anywhere():
    """The store must carry no birthdate. Fail on any birth/dob/usas column."""
    banned = ("birth", "dob", "usas")
    for table in Base.metadata.tables.values():
        for col in table.columns:
            assert not any(b in col.name.lower() for b in banned), (
                f"PII-shaped column {table.name}.{col.name}"
            )


def test_fixture_round_trips(session, meet_json):
    m = insert_meet(session, meet_json, imported_by="test")
    session.commit()

    assert m.season == 2026
    assert m.fmt == "sdif-v3"
    assert m.age_profile == "gpsa"

    assert session.query(Athlete).count() == len(meet_json["swimmers"])
    assert session.query(Event).count() == len(meet_json["events"])
    assert session.query(Result).count() > 0
    assert session.query(RelayResult).count() > 0

    # Team scores summed by the loader match the known golden totals.
    scores = {mt.team.code: mt.score for mt in session.query(MeetTeam).all()}
    assert scores == {"GG": 320, "WW": 146}


def test_athlete_identity_is_dob_free_and_season_scoped(session, meet_json):
    insert_meet(session, meet_json, imported_by="test")
    session.commit()

    a = session.query(Athlete).first()
    assert a.season == 2026
    assert "|" in a.name_key and a.name_key == a.name_key.upper()
    assert a.age_group  # age-group label stands in for the birthdate
    # No attribute leaks a birthdate.
    assert not hasattr(a, "birth_date")


def test_meet_key_is_idempotency_key(session, meet_json):
    insert_meet(session, meet_json)
    session.commit()

    # Same meet again → the unique meet_key rejects the duplicate.
    with pytest.raises(IntegrityError):
        insert_meet(session, meet_json)
        session.commit()
    session.rollback()

    # Key is stable and format-independent (date + sorted team codes).
    assert meet_key_for(meet_json) == "2026-06-29|GG,WW"


def test_un_leagued_meet_is_refused(session, meet_json):
    """A parse without a league still carries DOB — must never load."""
    meet_json.pop("ageProfile", None)
    with pytest.raises(ValueError, match="ageProfile"):
        insert_meet(session, meet_json)
