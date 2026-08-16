"""
SQLAlchemy Engine/Session-Setup.

connect_args={"check_same_thread": False} ist nur für SQLite nötig
(FastAPI kann Requests in unterschiedlichen Threads bearbeiten; SQLite-
Connections sind sonst an einen Thread gebunden - Postgres-Connections
haben diese Einschränkung nicht).
"""
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=_connect_args)


if engine.dialect.name == "sqlite":
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        """SQLite enforced `ondelete="CASCADE"`/`SET NULL` FKs nur, wenn diese
        PRAGMA pro Connection gesetzt ist - Postgres erzwingt Foreign-Keys
        ohnehin immer, der Listener wird dort nicht gebraucht."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


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
