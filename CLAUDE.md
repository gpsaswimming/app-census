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
  age-up date + age bands + scoring values + the **team registry** (canonical
  codes + aliases), passed into swimparse via `--league-file`. Its keys mirror
  swimparse's `gpsa.json` exactly (no remap); `tests/test_league_profile.py`
  guards the equality. Don't re-encode scoring, the age-up date, or team codes
  anywhere else. swimparse canonicalizes drifting team codes (`GWRA`→`WYTH`,
  `MBKM`→`MBKMT`) at parse time from this registry; `leagues.canonical_team_code`
  reuses the same map so reference-data importers (divisions) resolve aliases too.
- **DB is the source of truth.** No parallel canonical-JSON archive; a rebuild
  re-processes raw files. Keep the schema (Alembic-migrated) as the contract
  between ingest and dashboard.

## Layout

```
ingest/      FastAPI write side — owns the swimparse call        [Phase 3]
dashboard/   Streamlit read side — read-only over Postgres       [Phase 4]
  analysis/  ported tabs (overview, alignment, team_analytics, qt_*, division_setup)
  utils/     filters, division_config (read-only reader)
db/          SQLAlchemy models (db/models.py) + Alembic          [Phase 2/4]
leagues/     league profiles (gpsa.yaml) + load_profile()        [Phase 0 ✓]
scripts/     reference-data importers (standards, divisions)     [Phase 4]
data/        reference CSVs: standards/ (per-era) + vpsu_standards_2025.csv
division_configs/  divisions.csv (season → team → red/white/blue)
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
- **4 ✓** ported `gpsa-census` analytics onto the new schema (`dashboard/analysis`,
  `dashboard/utils`), read-only. `league_age` replaced by `athletes.age_group_lower/upper`
  (band-containment matching). Reference tables + migration 0002 (`city_meet_standards`,
  `division_configurations`, `excluded_athletes`), seeded by `scripts/import_*`. Baseline
  0001 frozen + drift test. `meet_type` supplied at ingest (form/n8n/backfill). No Python
  SDIF parser here. Retiring gpsa-census's `sdif_parser.py`/`import_data.py` is a Phase-5
  cutover step.
- **5** backfill all historical meets; reconcile against `gpsa-census`; stand up the
  private raw-file archive.

## swimparse contract

swimparse emits a `NormalizedMeet`; with `--league gpsa` it is DOB-free, age-grouped,
and stamped `ageProfile: "gpsa"`. Identity keys in that output are `name|ageGroup`
(per-meet, not cross-season) — the durable cross-season athlete identity is assigned
HERE (Phase 2), not in swimparse.
