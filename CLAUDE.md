# CLAUDE.md — app-census

Guidance for Claude Code when working in this repository.

## What this is

The successor to `gpsa-census`: GPSA swim-meet ingest + analytics, rebuilt as two
apps over Postgres with **no swimmer DOB at rest**. It ingests `.sd3` and `.hy3`
via the shared `swimparse` engine (`../app-tools/swimparse`).

Repo: `github.com/gpsaswimming/app-census` (public, inert code). The raw source
archive, derived data, prod CI/CD, and secrets live **privately** (self-hosted
GitLab) — never here.

## Non-negotiables

- **Never persist DOB.** swimparse computes the census age-group at parse time and
  strips the birthdate; only the age-group label is stored. No `birth_date` column,
  ever. (The old `gpsa-census` stored it — do not carry that over.)
- **Never commit raw `.sd3`/`.hy3`** (minors' DOBs). `.gitignore` blocks those
  extensions; use sanitized, DOB-free fixtures in `fixtures/`.
- **One league profile.** `leagues/gpsa.yaml` is the single source of truth for
  age-up date + age bands + scoring values, passed into swimparse via
  `--league-file`. Its keys mirror swimparse's `gpsa.json` exactly (no remap);
  `tests/test_league_profile.py` guards the equality. Don't re-encode scoring or
  the age-up date anywhere else.
- **DB is the source of truth.** No parallel canonical-JSON archive; a rebuild
  re-processes raw files. Keep the schema (Alembic-migrated) as the contract
  between ingest and dashboard.

## Layout

```
ingest/      FastAPI write side — owns the swimparse call        [Phase 3]
dashboard/   Streamlit read side — read-only over Postgres       [Phase 4]
db/          SQLAlchemy models (db/models.py) + Alembic          [Phase 2]
leagues/     league profiles (gpsa.yaml) + load_profile()        [Phase 0 ✓]
fixtures/    sanitized DOB-free NormalizedMeet JSON
tests/       pytest (rootdir import via pyproject pythonpath=".")
```

## Commands

```bash
pip install -r requirements-dev.txt && pytest   # tests, no Docker
docker compose up --build                        # db + ingest + dashboard (127.0.0.1)
```

## Phase map (see ../app-census-migration-plan.md)

- **0 ✓** scaffold + league YAML (this).
- **2** Postgres schema + Alembic. DOB-free tables from NormalizedMeet. Resolve the
  cross-season **athlete identity key without DOB** here (the old repo used
  `(season, name_key, birth_date)` — replace `birth_date` with age-group + team +
  gender, or a manual-merge scheme; see the migration plan's open decision).
- **3** ingest service; vendor the swimparse CLI in the container (recommended
  parse boundary). score() cross-check as the correctness gate. Pangolin auth.
- **4** port `gpsa-census` analytics onto the new schema; retire that repo's
  `sdif_parser.py` + `import_data.py`.
- **5** backfill all historical meets; reconcile against `gpsa-census`; stand up the
  private raw-file archive.

## swimparse contract

swimparse emits a `NormalizedMeet`; with `--league gpsa` it is DOB-free, age-grouped,
and stamped `ageProfile: "gpsa"`. Identity keys in that output are `name|ageGroup`
(per-meet, not cross-season) — the durable cross-season athlete identity is assigned
HERE (Phase 2), not in swimparse.
