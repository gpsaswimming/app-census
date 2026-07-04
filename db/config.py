"""Database connection configuration.

The store is Postgres and the single source of truth (there is no separate
canonical-JSON layer — a rebuild re-processes the raw source files). Both the
ingest service and the dashboard read ``DATABASE_URL`` from the environment.
"""

from __future__ import annotations

import os

# Local-dev default matches docker-compose.yml. Prod injects a real secret.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://census:census@localhost:5432/census",
)
