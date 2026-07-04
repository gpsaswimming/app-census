"""baseline schema (DOB-free NormalizedMeet tables)

Revision ID: 0001_baseline
Revises:
Create Date: 2026-07-04

The baseline creates the whole schema straight from the ORM metadata so it can
never drift from db/models.py. Subsequent changes use
`alembic revision --autogenerate`, which emits explicit op.* calls.
"""
from alembic import op

from db.models import Base

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
