"""Ingest service (FastAPI) — the write side of app-census.

Two actors hit the same pipeline:
  * n8n / scripts  → POST /preview and POST /commit (multipart file upload)
  * a human        → GET / serves a thin upload form that calls those endpoints

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
    profile = load_profile("gpsa")
    return {"status": "ok", "league": profile["id"], "phase": 3}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_PUBLIC / "index.html")


async def _read(file: UploadFile) -> bytes:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty upload")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large")
    return data


@app.post("/preview")
async def preview(file: UploadFile) -> dict:
    """Dry run: parse + validate, return a summary. No database write."""
    data = await _read(file)
    try:
        return service.preview(data, file.filename or "meet.sd3")
    except (service.IngestError, SwimparseError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/commit")
async def commit(
    file: UploadFile,
    imported_by: str | None = Form(default=None),
    session: Session = Depends(get_session),
) -> dict:
    """Parse + validate + idempotently upsert to Postgres. Writes an audit row."""
    data = await _read(file)
    try:
        return service.commit(session, data, file.filename or "meet.sd3", imported_by=imported_by)
    except (service.IngestError, SwimparseError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
