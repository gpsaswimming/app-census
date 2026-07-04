"""Shared test fixtures + skip helpers.

The ingest tests need Node and the sibling swimparse checkout (the real parse
boundary). When either is missing they skip rather than fail, so the DB-only
tests still run in a bare environment.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool


def make_sqlite_engine():
    """In-memory SQLite that ENFORCES foreign keys (off by default in SQLite).

    Real Postgres enforces FKs; matching that locally is what catches
    delete/replace ordering bugs in the fast test loop. StaticPool keeps the one
    :memory: connection alive across sessions.
    """
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _fk_pragma(dbapi_conn, _):  # noqa: ANN001
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine

_SWIMPARSE = Path(__file__).resolve().parents[2] / "app-tools" / "swimparse"
_RAW_FIXTURES = _SWIMPARSE / "test" / "fixtures"

needs_swimparse = pytest.mark.skipif(
    not (shutil.which("node") and (_SWIMPARSE / "cli.js").exists()),
    reason="needs Node + the sibling app-tools/swimparse checkout",
)


@pytest.fixture()
def raw_sd3() -> bytes:
    f = _RAW_FIXTURES / "gg-at-ww.sd3"
    if not f.exists():
        pytest.skip(f"sanitized raw fixture not found: {f}")
    return f.read_bytes()
