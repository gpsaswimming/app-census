"""Alembic environment. URL comes from DATABASE_URL (db.config); metadata from
db.models so `alembic revision --autogenerate` works for future changes."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure the repo root is importable regardless of the cwd alembic runs from.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alembic import context
from sqlalchemy import engine_from_config, pool

from db.config import DATABASE_URL as _DEFAULT_URL
from db.models import Base

# Read the URL from the environment at RUN time, not from the cached
# db.config constant. db.config evaluates DATABASE_URL once at import, so if
# something imported it earlier (e.g. a test harness) the constant is frozen —
# and alembic would then migrate the wrong database. Resolving it here per
# invocation keeps `alembic upgrade` and the tests pointed where the caller means.
DATABASE_URL = os.getenv("DATABASE_URL", _DEFAULT_URL)

config = context.config
config.set_main_option("sqlalchemy.url", DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
