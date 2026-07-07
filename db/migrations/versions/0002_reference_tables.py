"""reference tables + athlete age-group bounds

Revision ID: 0002_reference_tables
Revises: 0001_baseline
Create Date: 2026-07-05

Phase 4: the analytics inputs the dashboard reads but the ingest pipeline does
not produce — City Meet standards, division assignments, and QT exclusions —
plus the integer age-group bounds on ``athletes`` that replace the old exact
``league_age`` for qualification matching. All DOB-free.
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_reference_tables"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("athletes", sa.Column("age_group_lower", sa.Integer(), nullable=True))
    op.add_column("athletes", sa.Column("age_group_upper", sa.Integer(), nullable=True))

    op.create_table(
        "city_meet_standards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=12), nullable=True),
        sa.Column("gender", sa.String(length=1), nullable=True),
        sa.Column("age_group_lower", sa.Integer(), nullable=True),
        sa.Column("age_group_upper", sa.Integer(), nullable=True),
        sa.Column("distance", sa.Integer(), nullable=True),
        sa.Column("stroke", sa.String(length=50), nullable=True),
        sa.Column("standard_seconds", sa.Float(), nullable=True),
        sa.Column("standard_formatted", sa.String(length=20), nullable=True),
        sa.Column("season_start", sa.Integer(), nullable=False),
        sa.Column("season_end", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_city_meet_standards_season_start", "city_meet_standards", ["season_start"]
    )
    op.create_index(
        "ix_city_meet_standards_season_end", "city_meet_standards", ["season_end"]
    )

    op.create_table(
        "division_configurations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("division", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("season", "team_id", name="uq_division_season_team"),
    )
    op.create_index(
        "ix_division_configurations_season", "division_configurations", ["season"]
    )
    op.create_index(
        "ix_division_configurations_team_id", "division_configurations", ["team_id"]
    )

    op.create_table(
        "excluded_athletes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_excluded_athletes_athlete_id",
        "excluded_athletes",
        ["athlete_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_excluded_athletes_athlete_id", table_name="excluded_athletes")
    op.drop_table("excluded_athletes")

    op.drop_index(
        "ix_division_configurations_team_id", table_name="division_configurations"
    )
    op.drop_index(
        "ix_division_configurations_season", table_name="division_configurations"
    )
    op.drop_table("division_configurations")

    op.drop_index(
        "ix_city_meet_standards_season_end", table_name="city_meet_standards"
    )
    op.drop_index(
        "ix_city_meet_standards_season_start", table_name="city_meet_standards"
    )
    op.drop_table("city_meet_standards")

    op.drop_column("athletes", "age_group_upper")
    op.drop_column("athletes", "age_group_lower")
