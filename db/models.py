"""SQLAlchemy models (DOB-free) derived from the swimparse NormalizedMeet shape.

Design constraints (from the migration plan):
  * DOB is NEVER a column. Only the computed age-group label is stored. A test
    (test_schema.py) scans every column name and fails on birth/dob/usas.
  * Athlete identity is **season-scoped**, keyed on
    (season, name_key, gender, age_group, team) — the proven gpsa-census model
    with the age-group label standing in for the birthdate. One row per swimmer
    per season; cross-season progression is matched by (name_key, gender).
  * `Meet.meet_key` is the idempotency key that drives upsert (Phase 3) so a
    re-ingest of the same meet does not double-count.
  * Provenance: age_profile, source_filename, source_software, imported_at/by.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Declarative base for all app-census tables."""


class Team(Base):
    """A league team (cross-season; codes normalized to canonical at ingest)."""

    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    full_code: Mapped[str | None] = mapped_column(String(24))
    name: Mapped[str | None] = mapped_column(String(200))

    meets_hosted: Mapped[list[Meet]] = relationship(back_populates="host_team")


class Meet(Base):
    """One meet. `meet_key` is the idempotency key for upsert."""

    __tablename__ = "meets"

    id: Mapped[int] = mapped_column(primary_key=True)
    meet_key: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    date: Mapped[str | None] = mapped_column(String(10), index=True)  # YYYY-MM-DD
    season: Mapped[int | None] = mapped_column(Integer, index=True)   # YYYY
    meet_type: Mapped[str | None] = mapped_column(String(20), index=True)  # dual/invitational/city_meet/exhibition
    course: Mapped[str | None] = mapped_column(String(4))
    fmt: Mapped[str | None] = mapped_column("format", String(16))     # sdif-v3 / hy3

    # Provenance
    age_profile: Mapped[str | None] = mapped_column(String(32))       # e.g. "gpsa"
    source_software: Mapped[str | None] = mapped_column(String(64))
    source_filename: Mapped[str | None] = mapped_column(String(255))
    host_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    imported_by: Mapped[str | None] = mapped_column(String(120))

    host_team: Mapped[Team | None] = relationship(back_populates="meets_hosted")
    teams: Mapped[list[MeetTeam]] = relationship(back_populates="meet", cascade="all, delete-orphan")
    events: Mapped[list[Event]] = relationship(back_populates="meet", cascade="all, delete-orphan")


class MeetTeam(Base):
    """Team participation + final score in a meet."""

    __tablename__ = "meet_teams"
    __table_args__ = (UniqueConstraint("meet_id", "team_id", name="uq_meet_team"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    meet_id: Mapped[int] = mapped_column(ForeignKey("meets.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)

    meet: Mapped[Meet] = relationship(back_populates="teams")
    team: Mapped[Team] = relationship()


class Athlete(Base):
    """A swimmer, **season-scoped**. Identity carries no birthdate.

    The unique key (season, name_key, gender, age_group, team) is the DOB-free
    replacement for gpsa-census's (season, name_key, birth_date): the 2-year
    age-group band plus team + gender stand in for the birthdate. Same-name
    collisions inside one band/team/season are rare and surfaced by an audit
    report (Phase 4), never auto-merged.
    """

    __tablename__ = "athletes"
    __table_args__ = (
        UniqueConstraint(
            "season", "name_key", "gender", "age_group", "team_id", name="uq_athlete_identity"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    season: Mapped[int] = mapped_column(Integer, index=True)
    name_key: Mapped[str] = mapped_column(String(200), index=True)  # "LAST|FIRST" upper
    last_name: Mapped[str | None] = mapped_column(String(100))
    first_name: Mapped[str | None] = mapped_column(String(100))
    full_name: Mapped[str | None] = mapped_column(String(200))
    gender: Mapped[str | None] = mapped_column(String(1))
    age_group: Mapped[str | None] = mapped_column(String(16))  # label, e.g. "9-10"
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    team: Mapped[Team] = relationship()
    results: Mapped[list[Result]] = relationship(back_populates="athlete")
    relay_legs: Mapped[list[RelayLeg]] = relationship(back_populates="athlete")


class Event(Base):
    """An event within a meet. `age_group` here is the bracket swum (may differ
    from a swimmer's own age-group when they swim up)."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    meet_id: Mapped[int] = mapped_column(ForeignKey("meets.id"), index=True)
    event_number: Mapped[str | None] = mapped_column(String(10), index=True)  # alphanumeric
    event_type: Mapped[str] = mapped_column(String(12))  # individual / relay
    gender: Mapped[str | None] = mapped_column(String(1))  # M / F / X
    age_group: Mapped[str | None] = mapped_column(String(20))
    age_group_lower: Mapped[int | None] = mapped_column(Integer)
    age_group_upper: Mapped[int | None] = mapped_column(Integer)
    distance: Mapped[int | None] = mapped_column(Integer)
    stroke: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String(200))

    meet: Mapped[Meet] = relationship(back_populates="events")
    results: Mapped[list[Result]] = relationship(back_populates="event", cascade="all, delete-orphan")
    relay_results: Mapped[list[RelayResult]] = relationship(back_populates="event", cascade="all, delete-orphan")


class Result(Base):
    """An individual swim."""

    __tablename__ = "results"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    athlete_id: Mapped[int | None] = mapped_column(ForeignKey("athletes.id"), index=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), index=True)
    seed_seconds: Mapped[float | None] = mapped_column(Float)
    time_seconds: Mapped[float | None] = mapped_column(Float, index=True)
    time_formatted: Mapped[str | None] = mapped_column(String(20))
    place: Mapped[int | None] = mapped_column(Integer)
    points: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str | None] = mapped_column(String(12))  # ok/dq/ns/dnf/scratch/exhibition
    disqualified: Mapped[bool] = mapped_column(Boolean, default=False)

    event: Mapped[Event] = relationship(back_populates="results")
    athlete: Mapped[Athlete | None] = relationship(back_populates="results")
    team: Mapped[Team | None] = relationship()


class RelayResult(Base):
    """A relay swim."""

    __tablename__ = "relay_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), index=True)
    relay_letter: Mapped[str | None] = mapped_column(String(2))
    time_seconds: Mapped[float | None] = mapped_column(Float, index=True)
    time_formatted: Mapped[str | None] = mapped_column(String(20))
    place: Mapped[int | None] = mapped_column(Integer)
    points: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str | None] = mapped_column(String(12))
    disqualified: Mapped[bool] = mapped_column(Boolean, default=False)

    event: Mapped[Event] = relationship(back_populates="relay_results")
    team: Mapped[Team | None] = relationship()
    legs: Mapped[list[RelayLeg]] = relationship(back_populates="relay_result", cascade="all, delete-orphan")


class RelayLeg(Base):
    """A swimmer's leg on a relay. `athlete_id` may be null when the leg name
    can't be resolved to a season athlete."""

    __tablename__ = "relay_legs"

    id: Mapped[int] = mapped_column(primary_key=True)
    relay_result_id: Mapped[int] = mapped_column(ForeignKey("relay_results.id"), index=True)
    athlete_id: Mapped[int | None] = mapped_column(ForeignKey("athletes.id"), index=True)
    leg_order: Mapped[int | None] = mapped_column(Integer)
    swimmer_name: Mapped[str | None] = mapped_column(String(120))

    relay_result: Mapped[RelayResult] = relationship(back_populates="legs")
    athlete: Mapped[Athlete | None] = relationship(back_populates="relay_legs")


class ImportLog(Base):
    """Audit trail: one row per parse/preview/commit/reject of a source file."""

    __tablename__ = "import_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    meet_key: Mapped[str | None] = mapped_column(String(200), index=True)
    meet_id: Mapped[int | None] = mapped_column(ForeignKey("meets.id"))
    source_filename: Mapped[str | None] = mapped_column(String(255))
    fmt: Mapped[str | None] = mapped_column("format", String(16))
    age_profile: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str | None] = mapped_column(String(16))  # committed/rejected/previewed
    message: Mapped[str | None] = mapped_column(Text)
    num_events: Mapped[int | None] = mapped_column(Integer)
    num_results: Mapped[int | None] = mapped_column(Integer)
    team_scores: Mapped[dict | None] = mapped_column(JSON)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    imported_by: Mapped[str | None] = mapped_column(String(120))
