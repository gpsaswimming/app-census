"""Database package — the schema is the contract between ingest and dashboard.

Phase 0: declarative base + connection config only. Phase 2 adds the DOB-free
tables (teams, meets, athletes, events, results, relays, import_log) and the
Alembic baseline migration.
"""
