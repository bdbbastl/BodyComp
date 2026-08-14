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
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.core.database import Base, SessionLocal, engine  # noqa: F401 - SessionLocal wird von tests/conftest.py gepatcht
from app.core.migrate_users_nullable_password import fix_users_password_hash_nullable
from app.core.migrations import run_lightweight_migrations
from app.models import app_setting  # noqa: F401 - Import registriert Table bei create_all
from app.models import user  # noqa: F401 - Import registriert Table bei create_all
from app.models import client  # noqa: F401 - Import registriert Table bei create_all
from app.models import email_token  # noqa: F401 - Import registriert Table bei create_all
from app.routers import auth, clients, comparisons, day_logs, photos, poses, settings as settings_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    run_lightweight_migrations(engine)
    fix_users_password_hash_nullable(engine)
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

# Wird von authlib fürs Google-OAuth-State/Nonce-Handling gebraucht
# (request.session) - siehe routers/auth.py google_login/google_callback.
# Middleware-Reihenfolge: Starlette führt Middlewares in umgekehrter
# Registrierungsreihenfolge aus (zuletzt hinzugefügt = äußerste Schicht),
# das spielt hier aber keine Rolle, da CORS und Session unabhängig sind.
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret_key)

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
