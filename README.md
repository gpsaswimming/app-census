# app-census

GPSA swim-meet **census**: ingest dual/invitational/championship results and serve
longitudinal analytics — rebuilt as two small apps over Postgres, with **no swimmer
birthdates stored at rest**.

This is the successor to `gpsa-census`. It ingests `.sd3` **and** `.hy3` through the
shared [`swimparse`](../app-tools/swimparse) engine, splits ingestion from
presentation, and minimizes PII.

## Architecture

```
  raw .sd3/.hy3 ─► swimparse (+ leagues/gpsa.yaml) ─► DOB-FREE NormalizedMeet JSON
                                                            │ (age-group stamped)
              n8n API ──┬── manual web upload ─────────────┘
                        ▼
            ┌─────────────────────────┐
            │  ingest  (FastAPI)      │  parse → preview → confirm → commit
            │  owns the swimparse call│  idempotent · score() gate · audited
            └───────────┬─────────────┘
                        ▼  upsert
            ┌─────────────────────────┐
            │  Postgres  (the store)  │  ◄── source of truth; DOB-free
            └───────────┬─────────────┘
                        ▼  read-only
            ┌─────────────────────────┐
            │  dashboard  (Streamlit) │  analytics
            └─────────────────────────┘

  private raw-file archive (.sd3/.hy3, DOB-bearing) = the only rebuild path
```

### Key decisions

- **Age-group only at rest.** DOB is never persisted — swimparse computes the
  age-group at the parse boundary and drops the birthdate. The store holds the
  label (e.g. `9-10`), never a birthdate.
- **DB is the source of truth.** No separate canonical-JSON layer; a rebuild
  re-processes the raw source files. The private raw-file archive is the real
  disaster-recovery asset.
- **One league profile.** [`leagues/gpsa.yaml`](leagues/gpsa.yaml) carries the
  age-up date, age bands, and scoring values, and is passed straight into
  swimparse. Season-stable (no year in the id).
- **Public / private split.** This repo is inert public code + configs +
  sanitized fixtures. The raw archive, the derived Postgres data, prod CI/CD, and
  secrets live privately (self-hosted GitLab).

## Layout

```
ingest/      FastAPI write side (parse → preview → confirm → commit)   [Phase 3]
dashboard/   Streamlit read side (analytics)                           [Phase 4]
db/          SQLAlchemy models + Alembic migrations                    [Phase 2]
leagues/     league profiles passed into swimparse (gpsa.yaml)         [Phase 0 ✓]
fixtures/    sanitized, DOB-free NormalizedMeet JSON for tests
tests/       contract + unit tests
docker-compose.yml   local db + ingest + dashboard
```

## Status

Phase 0 (this scaffold) is a runnable shell. Build order on the critical path:
**0 → 2 → 3 → 4 → 5** (see `../app-census-migration-plan.md`).

## Develop

```bash
# Tests (no Docker needed)
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest

# Full stack
docker compose up --build          # db:5432, ingest:8000, dashboard:8501
curl localhost:8000/health
```

## Privacy

Never commit raw `.sd3`/`.hy3` (minors' DOBs) — `.gitignore` blocks those
extensions; use sanitized fixtures. See the fixture-sanitization guardrail.
