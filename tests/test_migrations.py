"""Alembic up/down against a real Postgres.

These tests are DESTRUCTIVE — they ``downgrade base`` (drop every table). They
run only when ``CENSUS_TEST_DATABASE_URL`` points at a **throwaway** database
whose name contains ``test`` (e.g. ``…/census_test``). Pointing them at a real
database (``…/census``) is refused, so a stray env var can't wipe live data.

    docker compose exec db psql -U census -d postgres -c 'CREATE DATABASE census_test;'
    CENSUS_TEST_DATABASE_URL=postgresql+psycopg://census:census@localhost:5432/census_test pytest

Verifies the migrations run both ways and exactly reproduce the models.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_DB = os.getenv("CENSUS_TEST_DATABASE_URL")
_ALEMBIC_INI = Path(__file__).resolve().parents[1] / "db" / "alembic.ini"


def _is_throwaway(url: str | None) -> bool:
    """True only for a DB whose name marks it as a disposable test database."""
    if not url:
        return False
    db_name = url.rsplit("/", 1)[-1].split("?", 1)[0].lower()
    return "test" in db_name


# Guardrail: refuse to run the drop-all tests against anything not clearly a
# throwaway DB. Skips (loudly) rather than risk wiping a real database.
_SAFE = _is_throwaway(_DB)
_skip_reason = (
    "set CENSUS_TEST_DATABASE_URL to a throwaway db whose name contains 'test' "
    "(these tests DROP ALL TABLES)"
)


@pytest.mark.skipif(not _SAFE, reason=_skip_reason)
def test_upgrade_downgrade_upgrade():
    os.environ["DATABASE_URL"] = _DB  # env.py reads this
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_ALEMBIC_INI))
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


@pytest.mark.skipif(not _SAFE, reason=_skip_reason)
def test_migrations_match_models():
    """The hand-written migrations must exactly reproduce ``Base.metadata``.

    Migrate a fresh DB to head, then autogenerate-compare it against the live
    models. Any difference (a column/table the baseline forgot, or a model change
    with no migration) shows up as an op directive and fails the test — the
    guard that keeps the frozen baseline honest.
    """
    os.environ["DATABASE_URL"] = _DB
    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from sqlalchemy import create_engine

    from db.models import Base

    cfg = Config(str(_ALEMBIC_INI))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    engine = create_engine(_DB)
    with engine.connect() as conn:
        mc = MigrationContext.configure(conn, opts={"compare_type": True})
        diff = compare_metadata(mc, Base.metadata)
    engine.dispose()

    assert diff == [], f"schema drift between migrations and models:\n{diff}"
