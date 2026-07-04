"""SQLAlchemy models (DOB-free) derived from the swimparse NormalizedMeet shape.

Phase 0: declarative base only. Phase 2 defines the tables:
  teams, meets, athletes (DOB-free identity — key TBD), events, results,
  relays, relay_legs, import_log.

Design constraints carried from the migration plan:
  * DOB is NEVER a column. Only the computed age-group label is stored.
  * A meet-identity / idempotency key drives upsert (re-ingest must not double).
  * Provenance columns: age_profile, source filename, imported_at / imported_by.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all app-census tables."""
