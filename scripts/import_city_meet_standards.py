"""Import City Meet qualifying standards from per-era CSV files into Postgres.

Standards are season-scoped: each CSV in ``data/standards/`` holds one adopted
set, and its effective-season range is taken from the file name:

    data/standards/2023-2025.csv  -> seasons 2023 through 2025 (inclusive)
    data/standards/2026-2027.csv  -> seasons 2026 through 2027 (inclusive)
    data/standards/2028.csv       -> season 2028 only

A swim is later judged against the set whose range covers the swim's season, so
historical qualification analysis uses the standards actually in effect that
year. Ranges must not overlap.

Reference data — safe for the public repo (no PII). Reads ``DATABASE_URL`` from
the environment (see db.config); defaults to the local docker-compose Postgres.

Usage:
    python scripts/import_city_meet_standards.py            # scan data/standards
    python scripts/import_city_meet_standards.py --csv path/to/2026-2027.csv
"""

from __future__ import annotations

import argparse
import csv
import glob
import os
import re
import sys
from pathlib import Path

# Repo root importable regardless of cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.models import CityMeetStandard  # noqa: E402
from db.session import SessionLocal  # noqa: E402

# Effective-season range encoded in the file stem: "2023-2025" or "2028".
_RANGE_RE = re.compile(r"^(\d{4})(?:-(\d{4}))?$")


def parse_season_range(csv_path: str) -> tuple[int, int]:
    """Parse an inclusive ``(season_start, season_end)`` from a standards file name."""
    stem = Path(csv_path).stem
    match = _RANGE_RE.match(stem)
    if not match:
        raise ValueError(
            f"Standards file '{csv_path}' must be named YYYY.csv or YYYY-YYYY.csv "
            f"to encode its effective-season range (got stem '{stem}')."
        )
    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else start
    if end < start:
        raise ValueError(f"Standards file '{csv_path}' has end season before start season.")
    return start, end


def _read_era(csv_path: str, season_start: int, season_end: int) -> list[CityMeetStandard]:
    """Read one era CSV into (unsaved) CityMeetStandard rows tagged with its range."""
    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(
                CityMeetStandard(
                    event_type="individual",
                    gender="M" if row["gender"] == "M" else "F",
                    age_group_lower=int(row["age_lower"]),
                    age_group_upper=int(row["age_upper"]),
                    distance=int(row["distance"]),
                    stroke=row["stroke"],
                    standard_seconds=float(row["standard_seconds"]),
                    standard_formatted=row["standard_time"],
                    season_start=season_start,
                    season_end=season_end,
                )
            )
    return rows


def import_standards(standards_dir: str | None = None, csv_path: str | None = None) -> bool:
    """Import all season-scoped City Meet standards, replacing any existing set."""
    print("=" * 70)
    print("City Meet Standards Import (season-scoped)")
    print("=" * 70)
    print()

    era_files = [csv_path] if csv_path else sorted(glob.glob(os.path.join(standards_dir, "*.csv")))
    if not era_files:
        print(f"Error: no standards CSV files found at: {csv_path or standards_dir}")
        return False

    # Parse ranges and read rows before touching the DB, so a bad file aborts cleanly.
    eras = []  # (path, start, end, rows)
    for path in era_files:
        if not os.path.exists(path):
            print(f"Error: CSV file not found: {path}")
            return False
        try:
            start, end = parse_season_range(path)
        except ValueError as e:
            print(f"✗ {e}")
            return False
        eras.append((path, start, end, _read_era(path, start, end)))

    # Guard against overlapping ranges (a swim must map to exactly one set).
    ordered = sorted(eras, key=lambda e: e[1])
    for (p1, s1, e1, _), (p2, s2, e2, _) in zip(ordered, ordered[1:]):
        if s2 <= e1:
            print(
                f"✗ Overlapping effective-season ranges: "
                f"{Path(p1).name} ({s1}-{e1}) and {Path(p2).name} ({s2}-{e2})."
            )
            return False

    session = SessionLocal()
    try:
        deleted = session.query(CityMeetStandard).delete()
        print(f"Removed {deleted} existing standards\n")

        imported = 0
        for path, start, end, rows in ordered:
            session.add_all(rows)
            imported += len(rows)
            span = f"{start}" if start == end else f"{start}-{end}"
            print(f"  {Path(path).name:<20} → seasons {span:<10} ({len(rows)} standards)")

        session.commit()
        print(f"\n✓ Imported {imported} standards across {len(ordered)} era(s)\n")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"✗ Error committing to database: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import season-scoped City Meet standards from per-era CSV files"
    )
    parser.add_argument("--dir", default="data/standards", help="Directory of per-era CSVs")
    parser.add_argument("--csv", default=None, help="Import a single era CSV instead of --dir")
    args = parser.parse_args()

    ok = import_standards(standards_dir=args.dir, csv_path=args.csv)
    if ok:
        print("City Meet standards imported. Restart the dashboard to see the changes.")
    else:
        print("Import failed. Please check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
