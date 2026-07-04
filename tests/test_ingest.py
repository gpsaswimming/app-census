"""End-to-end ingest: upload → swimparse → validate → upsert.

Uses FastAPI's TestClient against in-memory SQLite (shared via StaticPool) with
the DB dependency overridden. Needs Node + the sibling swimparse checkout.
"""

from __future__ import annotations

import pytest
from conftest import make_sqlite_engine, needs_swimparse
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base, Meet, MeetTeam, Result
from db.session import get_session
from ingest.app import app

pytestmark = needs_swimparse


@pytest.fixture()
def client_and_engine():
    engine = make_sqlite_engine()
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

    def override():
        s = TestSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = override
    with TestClient(app) as client:
        yield client, engine
    app.dependency_overrides.clear()


def _upload(raw: bytes):
    return {"file": ("gg-at-ww.sd3", raw, "application/octet-stream")}


def test_preview_summarizes_without_writing(client_and_engine, raw_sd3):
    client, engine = client_and_engine
    r = client.post("/preview", files=_upload(raw_sd3))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["season"] == 2026
    assert body["ageProfile"] == "gpsa"
    assert body["numSwimmers"] == 129
    assert body["teamScores"] == {"GG": 320, "WW": 146}
    # Nothing was written.
    with Session(engine) as s:
        assert s.query(Meet).count() == 0


def test_commit_is_idempotent(client_and_engine, raw_sd3):
    client, engine = client_and_engine

    r1 = client.post("/commit", files=_upload(raw_sd3), data={"imported_by": "tester"})
    assert r1.status_code == 200, r1.text
    assert r1.json()["status"] == "created"

    with Session(engine) as s:
        first_results = s.query(Result).count()
        assert s.query(Meet).count() == 1
        assert first_results > 0

    # Re-upload the same meet → update, not double-count.
    r2 = client.post("/commit", files=_upload(raw_sd3), data={"imported_by": "tester"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "updated"

    with Session(engine) as s:
        assert s.query(Meet).count() == 1
        assert s.query(Result).count() == first_results  # unchanged
        scores = {mt.team.code: mt.score for mt in s.query(MeetTeam).all()}
        assert scores == {"GG": 320, "WW": 146}


def test_garbage_file_is_rejected(client_and_engine):
    client, engine = client_and_engine
    r = client.post("/commit", files={"file": ("junk.sd3", b"this is not a meet", "text/plain")})
    assert r.status_code == 422
    with Session(engine) as s:
        assert s.query(Meet).count() == 0
