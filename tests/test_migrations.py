"""Alembic up/down against a real Postgres.

Skipped unless CENSUS_TEST_DATABASE_URL points at a throwaway Postgres (e.g. the
docker-compose `db` service). Verifies the baseline migrates cleanly both ways:
    upgrade head → downgrade base → upgrade head
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_DB = os.getenv("CENSUS_TEST_DATABASE_URL")
_ALEMBIC_INI = Path(__file__).resolve().parents[1] / "db" / "alembic.ini"


@pytest.mark.skipif(not _DB, reason="set CENSUS_TEST_DATABASE_URL to run migration tests")
def test_upgrade_downgrade_upgrade():
    os.environ["DATABASE_URL"] = _DB  # env.py reads this
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_ALEMBIC_INI))
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
