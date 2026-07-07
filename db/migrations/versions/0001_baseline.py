"""baseline schema (DOB-free NormalizedMeet tables)

Revision ID: 0001_baseline
Revises:
Create Date: 2026-07-04

Frozen snapshot of the Phase-2 schema. This baseline is explicit (not built from
live ``Base.metadata``) so it stays fixed as the models evolve: later phases add
incremental migrations (e.g. 0002) rather than mutating the baseline. A drift
test (tests/test_migrations.py) autogenerate-compares the migrated DB against the
current models and fails on any difference, so these hand-written ops can't
silently fall out of sync.
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("full_code", sa.String(length=24), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_teams_code", "teams", ["code"], unique=True)

    op.create_table(
        "meets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("meet_key", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("date", sa.String(length=10), nullable=True),
        sa.Column("season", sa.Integer(), nullable=True),
        sa.Column("meet_type", sa.String(length=20), nullable=True),
        sa.Column("course", sa.String(length=4), nullable=True),
        sa.Column("format", sa.String(length=16), nullable=True),
        sa.Column("age_profile", sa.String(length=32), nullable=True),
        sa.Column("source_software", sa.String(length=64), nullable=True),
        sa.Column("source_filename", sa.String(length=255), nullable=True),
        sa.Column("host_team_id", sa.Integer(), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("imported_by", sa.String(length=120), nullable=True),
        sa.ForeignKeyConstraint(["host_team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_meets_meet_key", "meets", ["meet_key"], unique=True)
    op.create_index("ix_meets_date", "meets", ["date"])
    op.create_index("ix_meets_season", "meets", ["season"])
    op.create_index("ix_meets_meet_type", "meets", ["meet_type"])

    op.create_table(
        "athletes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("name_key", sa.String(length=200), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("full_name", sa.String(length=200), nullable=True),
        sa.Column("gender", sa.String(length=1), nullable=True),
        sa.Column("age_group", sa.String(length=16), nullable=True),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "season", "name_key", "gender", "age_group", "team_id",
            name="uq_athlete_identity",
        ),
    )
    op.create_index("ix_athletes_season", "athletes", ["season"])
    op.create_index("ix_athletes_name_key", "athletes", ["name_key"])
    op.create_index("ix_athletes_team_id", "athletes", ["team_id"])

    op.create_table(
        "meet_teams",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("meet_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["meet_id"], ["meets.id"]),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meet_id", "team_id", name="uq_meet_team"),
    )
    op.create_index("ix_meet_teams_meet_id", "meet_teams", ["meet_id"])
    op.create_index("ix_meet_teams_team_id", "meet_teams", ["team_id"])

    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("meet_id", sa.Integer(), nullable=False),
        sa.Column("event_number", sa.String(length=10), nullable=True),
        sa.Column("event_type", sa.String(length=12), nullable=False),
        sa.Column("gender", sa.String(length=1), nullable=True),
        sa.Column("age_group", sa.String(length=20), nullable=True),
        sa.Column("age_group_lower", sa.Integer(), nullable=True),
        sa.Column("age_group_upper", sa.Integer(), nullable=True),
        sa.Column("distance", sa.Integer(), nullable=True),
        sa.Column("stroke", sa.String(length=50), nullable=True),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(["meet_id"], ["meets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_events_meet_id", "events", ["meet_id"])
    op.create_index("ix_events_event_number", "events", ["event_number"])

    op.create_table(
        "results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=True),
        sa.Column("team_id", sa.Integer(), nullable=True),
        sa.Column("seed_seconds", sa.Float(), nullable=True),
        sa.Column("time_seconds", sa.Float(), nullable=True),
        sa.Column("time_formatted", sa.String(length=20), nullable=True),
        sa.Column("place", sa.Integer(), nullable=True),
        sa.Column("points", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=True),
        sa.Column("disqualified", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"]),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_results_event_id", "results", ["event_id"])
    op.create_index("ix_results_athlete_id", "results", ["athlete_id"])
    op.create_index("ix_results_team_id", "results", ["team_id"])
    op.create_index("ix_results_time_seconds", "results", ["time_seconds"])

    op.create_table(
        "relay_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=True),
        sa.Column("relay_letter", sa.String(length=2), nullable=True),
        sa.Column("time_seconds", sa.Float(), nullable=True),
        sa.Column("time_formatted", sa.String(length=20), nullable=True),
        sa.Column("place", sa.Integer(), nullable=True),
        sa.Column("points", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=True),
        sa.Column("disqualified", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_relay_results_event_id", "relay_results", ["event_id"])
    op.create_index("ix_relay_results_team_id", "relay_results", ["team_id"])
    op.create_index("ix_relay_results_time_seconds", "relay_results", ["time_seconds"])

    op.create_table(
        "relay_legs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("relay_result_id", sa.Integer(), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=True),
        sa.Column("leg_order", sa.Integer(), nullable=True),
        sa.Column("swimmer_name", sa.String(length=120), nullable=True),
        sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"]),
        sa.ForeignKeyConstraint(["relay_result_id"], ["relay_results.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_relay_legs_relay_result_id", "relay_legs", ["relay_result_id"])
    op.create_index("ix_relay_legs_athlete_id", "relay_legs", ["athlete_id"])

    op.create_table(
        "import_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("meet_key", sa.String(length=200), nullable=True),
        sa.Column("meet_id", sa.Integer(), nullable=True),
        sa.Column("source_filename", sa.String(length=255), nullable=True),
        sa.Column("format", sa.String(length=16), nullable=True),
        sa.Column("age_profile", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("num_events", sa.Integer(), nullable=True),
        sa.Column("num_results", sa.Integer(), nullable=True),
        sa.Column("team_scores", sa.JSON(), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("imported_by", sa.String(length=120), nullable=True),
        sa.ForeignKeyConstraint(["meet_id"], ["meets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_import_log_meet_key", "import_log", ["meet_key"])


def downgrade() -> None:
    op.drop_index("ix_import_log_meet_key", table_name="import_log")
    op.drop_table("import_log")
    op.drop_index("ix_relay_legs_athlete_id", table_name="relay_legs")
    op.drop_index("ix_relay_legs_relay_result_id", table_name="relay_legs")
    op.drop_table("relay_legs")
    op.drop_index("ix_relay_results_time_seconds", table_name="relay_results")
    op.drop_index("ix_relay_results_team_id", table_name="relay_results")
    op.drop_index("ix_relay_results_event_id", table_name="relay_results")
    op.drop_table("relay_results")
    op.drop_index("ix_results_time_seconds", table_name="results")
    op.drop_index("ix_results_team_id", table_name="results")
    op.drop_index("ix_results_athlete_id", table_name="results")
    op.drop_index("ix_results_event_id", table_name="results")
    op.drop_table("results")
    op.drop_index("ix_events_event_number", table_name="events")
    op.drop_index("ix_events_meet_id", table_name="events")
    op.drop_table("events")
    op.drop_index("ix_meet_teams_team_id", table_name="meet_teams")
    op.drop_index("ix_meet_teams_meet_id", table_name="meet_teams")
    op.drop_table("meet_teams")
    op.drop_index("ix_athletes_team_id", table_name="athletes")
    op.drop_index("ix_athletes_name_key", table_name="athletes")
    op.drop_index("ix_athletes_season", table_name="athletes")
    op.drop_table("athletes")
    op.drop_index("ix_meets_meet_type", table_name="meets")
    op.drop_index("ix_meets_season", table_name="meets")
    op.drop_index("ix_meets_date", table_name="meets")
    op.drop_index("ix_meets_meet_key", table_name="meets")
    op.drop_table("meets")
    op.drop_index("ix_teams_code", table_name="teams")
    op.drop_table("teams")
