"""Import division assignments (Red/White/Blue) from CSV into Postgres.

Divisions are season-specific league configuration, version-controlled in
``division_configs/*.csv`` so the dashboard's read side stays read-only — edits
go through this importer, not the UI.

    season,team_code,division
    2025,MBKM,red
    2025,POQ,white

Team codes must already exist in the ``teams`` table (created by ingest). Reads
``DATABASE_URL`` from the environment (db.config). Reference data, no PII.

Usage:
    python scripts/import_divisions.py
    python scripts/import_divisions.py --file division_configs/divisions.csv
    python scripts/import_divisions.py --clear      # wipe assignments first
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# Repo root importable regardless of cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.models import DivisionConfiguration, Team  # noqa: E402
from db.session import SessionLocal  # noqa: E402
from leagues import canonical_team_code  # noqa: E402

_VALID_DIVISIONS = ("red", "white", "blue")


def import_divisions(csv_path: str, clear: bool = False) -> bool:
    """Import division assignments from ``csv_path``. Returns True on success."""
    csv_file = Path(csv_path)
    if not csv_file.exists():
        print(f"✗ Error: File not found: {csv_path}")
        return False

    session = SessionLocal()
    stats = {"processed": 0, "created": 0, "updated": 0, "skipped": 0, "errors": 0}
    by_season: dict[int, dict[str, int]] = {}
    try:
        if clear:
            n = session.query(DivisionConfiguration).delete()
            session.commit()
            print(f"✓ Cleared {n} existing division configurations\n")

        team_map = {t.code: t.id for t in session.query(Team).all()}
        print(f"Importing divisions from: {csv_path}")
        print(f"Found {len(team_map)} teams in database\n")

        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames or not all(
                c in reader.fieldnames for c in ("season", "team_code", "division")
            ):
                print("✗ Error: CSV must have columns: season, team_code, division")
                return False

            for row_num, row in enumerate(reader, start=2):
                stats["processed"] += 1
                try:
                    season = int(row["season"].strip())
                    # Canonicalize through the shared team registry so the CSV can
                    # carry drifting/legacy codes (e.g. MBKM) and still match the
                    # canonical code (MBKMT) that ingest stores.
                    team_code = canonical_team_code(row["team_code"].strip())
                    division = row["division"].strip().lower()
                except (ValueError, AttributeError) as e:
                    print(f"✗ Row {row_num}: Invalid data - {e}")
                    stats["errors"] += 1
                    continue

                if division not in _VALID_DIVISIONS:
                    print(f"✗ Row {row_num}: Invalid division '{division}'")
                    stats["errors"] += 1
                    continue
                if team_code not in team_map:
                    print(f"✗ Row {row_num}: Unknown team code '{team_code}'")
                    stats["errors"] += 1
                    continue

                team_id = team_map[team_code]
                by_season.setdefault(season, {"red": 0, "white": 0, "blue": 0})
                by_season[season][division] += 1

                existing = (
                    session.query(DivisionConfiguration)
                    .filter_by(season=season, team_id=team_id)
                    .first()
                )
                if existing:
                    if existing.division == division:
                        stats["skipped"] += 1
                    else:
                        print(
                            f"  Updated: {season} {team_code} → {division} "
                            f"(was {existing.division})"
                        )
                        existing.division = division
                        stats["updated"] += 1
                else:
                    session.add(
                        DivisionConfiguration(season=season, team_id=team_id, division=division)
                    )
                    stats["created"] += 1

        session.commit()
    finally:
        session.close()

    print("\n" + "=" * 60)
    print("Import Summary")
    print("=" * 60)
    print(f"Rows processed:      {stats['processed']}")
    print(f"New assignments:     {stats['created']}")
    print(f"Updated:             {stats['updated']}")
    print(f"Skipped (no change): {stats['skipped']}")
    print(f"Errors:              {stats['errors']}")
    if by_season:
        print("\nDivision Assignments by Season:")
        for season in sorted(by_season):
            c = by_season[season]
            total = sum(c.values())
            print(f"  {season}: Red={c['red']}, White={c['white']}, Blue={c['blue']} (Total: {total})")

    if stats["errors"] > 0:
        print("\n⚠️  Completed with errors (see above).")
        return False
    print("\n✓ Import completed successfully!")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Import division configurations from CSV")
    parser.add_argument("--file", default="division_configs/divisions.csv", help="Path to CSV")
    parser.add_argument("--clear", action="store_true", help="Clear all divisions first")
    args = parser.parse_args()

    if not import_divisions(args.file, clear=args.clear):
        sys.exit(1)


if __name__ == "__main__":
    main()
