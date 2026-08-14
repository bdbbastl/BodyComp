"""
FastAPI Entry-Point.

Für den POC: erzeugt Tabellen direkt via Base.metadata.create_all
(kein Alembic-Migrationslauf nötig). Für die spätere Cloud-Version
sollte das durch echte Alembic-Migrationen ersetzt werden.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import Base, SessionLocal, engine  # noqa: F401 - SessionLocal wird von tests/conftest.py gepatcht
from app.core.migrate_to_multitenancy import migrate_to_multitenancy
from app.core.migrations import run_lightweight_migrations
from app.models import app_setting  # noqa: F401 - Import registriert Table bei create_all
from app.models import user  # noqa: F401 - Import registriert Table bei create_all
from app.models import client  # noqa: F401 - Import registriert Table bei create_all
from app.routers import auth, clients, comparisons, day_logs, photos, poses, settings as settings_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    run_lightweight_migrations(engine)
    db = SessionLocal()
    try:
        migrate_to_multitenancy(
            db,
            email="basti.auer@outlook.com",
            password=settings.migration_seed_password,
            display_name="Basti",
        )
    finally:
        db.close()
    yield


app = FastAPI(title="BodyComp Tracker", version="0.1.0", lifespan=lifespan)

# Vite-Dev-Server läuft standardmäßig auf 5173.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Statische Auslieferung der Bilddateien (Originale + normalisierte
# Versionen) direkt aus dem lokalen data_dir.
app.mount("/media", StaticFiles(directory=settings.data_dir), name="media")

app.include_router(auth.router)
app.include_router(clients.router)
app.include_router(poses.router)
app.include_router(day_logs.router)
app.include_router(photos.router)
app.include_router(comparisons.router)
app.include_router(settings_router.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
