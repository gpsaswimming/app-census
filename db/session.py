"""Engine + session factory, shared by ingest (write) and dashboard (read)."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from db.config import DATABASE_URL

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def get_session() -> Session:
    """FastAPI dependency: yields a session, always closed."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
