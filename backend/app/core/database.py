"""
SQLAlchemy Engine/Session-Setup.

connect_args={"check_same_thread": False} ist nötig, weil FastAPI Requests
potenziell in unterschiedlichen Threads bearbeitet (Standard-Threadpool für
sync-Endpunkte); SQLite-Connections sind sonst an einen Thread gebunden.
"""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator:
    """FastAPI-Dependency: liefert eine DB-Session pro Request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
