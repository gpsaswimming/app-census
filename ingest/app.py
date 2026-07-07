"""Ingest service (FastAPI) — the write side of app-census.

Behind the reverse proxy this service owns two path prefixes on the shared host:
  * ``/ingest``     — the human upload form (GET) + its ``/ingest/app.js``
  * ``/api/*``      — the programmatic surface n8n / scripts hit
                      (``POST /api/preview``, ``POST /api/commit``)
``/health`` stays at the root for direct container/orchestration checks (it is
not routed through the proxy).

Auth is handled upstream by Pangolin (@gpsaswimming.org); this app implements
none of its own. Uploads are memory-only. The parse boundary (swimparse) makes
every stored meet DOB-free.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from db.session import get_session
from ingest import service
from ingest.swimparse_runner import SwimparseError
from leagues import load_profile

app = FastAPI(title="app-census ingest", version="0.1.0")

_PUBLIC = Path(__file__).resolve().parent / "public"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # generous; SDIF/HY3 dual meets are ~100 KB


@app.get("/health")
def health() -> dict:
    """Direct health check (not proxied) — for container/orchestration probes."""
    profile = load_profile("gpsa")
    return {"status": "ok", "league": profile["id"], "phase": 4}


# ── Upload form (human) ──────────────────────────────────────────────────────
# The form is a tiny internal tool; serve it uncached so a redeploy of the
# static assets always takes effect on the next reload (no stale app.js).
_NO_CACHE = {"Cache-Control": "no-cache"}


@app.get("/ingest")
def index() -> FileResponse:
    return FileResponse(_PUBLIC / "index.html", headers=_NO_CACHE)


@app.get("/ingest/app.js")
def app_js() -> FileResponse:
    return FileResponse(
        _PUBLIC / "app.js", media_type="application/javascript", headers=_NO_CACHE
    )


# ── Programmatic API (n8n / scripts / the form's fetch calls) ────────────────
async def _read(file: UploadFile) -> bytes:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty upload")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large")
    return data


@app.post("/api/preview")
async def preview(file: UploadFile) -> dict:
    """Dry run: parse + validate, return a summary. No database write."""
    data = await _read(file)
    try:
        return service.preview(data, file.filename or "meet.sd3")
    except (service.IngestError, SwimparseError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/commit")
async def commit(
    file: UploadFile,
    imported_by: str | None = Form(default=None),
    meet_type: str | None = Form(default=None),
    session: Session = Depends(get_session),
) -> dict:
    """Parse + validate + idempotently upsert to Postgres. Writes an audit row.

    ``meet_type`` (dual/invitational/city_meet/exhibition) is optional; the
    analytics dashboard filters on it.
    """
    data = await _read(file)
    try:
        return service.commit(
            session,
            data,
            file.filename or "meet.sd3",
            imported_by=imported_by,
            meet_type=meet_type or None,
        )
    except (service.IngestError, SwimparseError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
