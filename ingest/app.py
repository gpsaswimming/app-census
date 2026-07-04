"""Ingest service (FastAPI) — the write side of app-census.

Phase 0: a runnable shell exposing only health. Phase 3 adds the real pipeline:
upload .sd3/.hy3 → swimparse (gpsa league profile) → DOB-free NormalizedMeet →
validate (score() gate) → preview → confirm → idempotent upsert to Postgres →
import_log. Auth is handled upstream by Pangolin; this app implements none.
"""

from __future__ import annotations

from fastapi import FastAPI

from leagues import load_profile

app = FastAPI(title="app-census ingest", version="0.0.0")


@app.get("/health")
def health() -> dict:
    """Liveness probe. Confirms the service is up and the league profile loads."""
    profile = load_profile("gpsa")
    return {"status": "ok", "league": profile["id"], "phase": 0}


# Phase 3 endpoints (parse → preview → confirm → commit) land here.
