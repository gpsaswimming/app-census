#!/bin/sh
# Ingest container entrypoint: bring the schema up to head, then serve.
#
# The ingest service owns the write side / schema, so it (not the dashboard) runs
# migrations on startup. The db healthcheck gates this via compose depends_on, so
# Postgres is reachable by the time alembic runs. Idempotent — a no-op once the
# DB is already at head.
set -e

echo "[entrypoint] applying migrations (alembic upgrade head)…"
alembic -c db/alembic.ini upgrade head

echo "[entrypoint] starting ingest API…"
exec uvicorn ingest.app:app --host 0.0.0.0 --port 8000
