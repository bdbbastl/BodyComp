"""
Zentrale Konfiguration der Anwendung.

Bewusst über pydantic-settings gelöst, damit spätere Cloud-Deployments
(z.B. S3-Bucket statt lokalem Ordner, Postgres statt SQLite) nur über
Umgebungsvariablen umgeschaltet werden müssen, ohne Code anzufassen.
"""
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Lädt backend/.env in echte Prozess-Umgebungsvariablen (nicht nur ins
# Settings-Objekt unten) - nötig, damit z.B. der Anthropic-SDK-Client
# (services/ai_comparison.py) ANTHROPIC_API_KEY automatisch findet, ohne
# dass wir den Wert selbst durchreichen müssen.
load_dotenv()


class Settings(BaseSettings):
    # extra="ignore": .env enthält auch Variablen ohne BODYCOMP_-Präfix
    # (z.B. GEMINI_API_KEY für services/ai_comparison.py, gelesen direkt
    # aus os.environ) - die sollen hier nicht als unbekannte Felder crashen.
    model_config = SettingsConfigDict(env_prefix="BODYCOMP_", env_file=".env", extra="ignore")

    # Basisverzeichnis für alle lokalen Daten (POC: lokales Filesystem).
    # In der Cloud-Version würde hier ein Object-Storage-Adapter (S3/GCS)
    # dieselbe "StorageBackend"-Schnittstelle implementieren.
    data_dir: Path = Path(__file__).resolve().parents[2] / "data"

    # "local" (Default, lokale Entwicklung) oder "r2" (Produktion) - siehe
    # services/storage_sync.py.
    storage_backend: str = "local"
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = "bodycomp"

    @property
    def photos_incoming_dir(self) -> Path:
        """Nutzer wirft hier neue, noch unverarbeitete Fotos rein (Ordner-Sync)."""
        return self.data_dir / "photos_incoming"

    @property
    def photos_processed_dir(self) -> Path:
        """Original-/Vollbilder nach Zuordnung zu einer Pose, sortiert abgelegt."""
        return self.data_dir / "photos_processed"

    @property
    def photos_normalized_dir(self) -> Path:
        """Von MediaPipe normalisierte Versionen für den Overlay-Vergleich."""
        return self.data_dir / "photos_normalized"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "bodycomp.db"

    @property
    def database_url(self) -> str:
        import os

        env_url = os.environ.get("DATABASE_URL")
        if env_url:
            # Railway liefert "postgres://...", SQLAlchemy 2.x + psycopg
            # brauchen den Treiber explizit im Scheme ("postgresql+psycopg://").
            if env_url.startswith("postgres://"):
                env_url = env_url.replace("postgres://", "postgresql+psycopg://", 1)
            elif env_url.startswith("postgresql://"):
                env_url = env_url.replace("postgresql://", "postgresql+psycopg://", 1)
            return env_url
        return f"sqlite:///{self.db_path.as_posix()}"

    # Erlaubte Dateiendungen beim Ordner-Sync
    allowed_extensions: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".heic")

    # Signiert die Session-Cookies (siehe services/auth.py). In Produktion
    # per BODYCOMP_SESSION_SECRET_KEY überschreiben - der Default ist nur
    # fürs lokale Dev-Setup gedacht.
    session_secret_key: str = "dev-only-insecure-secret-change-me"

    # Google OAuth (siehe routers/auth.py). In Google Cloud Console
    # unter "APIs & Services > Credentials" anzulegen.
    google_client_id: str = ""
    google_client_secret: str = ""
    # Muss exakt der in der Google Cloud Console hinterlegten Redirect-URI
    # entsprechen. Lokal: http://localhost:8000/api/auth/google/callback
    google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"

    # Resend (transaktionaler E-Mail-Versand, siehe services/email.py).
    resend_api_key: str = ""
    # Absenderadresse - im Sandbox-Modus (keine verifizierte Domain) muss
    # das Resends Standard-Testadresse sein: onboarding@resend.dev
    email_from_address: str = "onboarding@resend.dev"

    # Basis-URL des Frontends, für Links in E-Mails (Bestätigung, Reset).
    frontend_base_url: str = "http://localhost:5173"

    # Leer = Sentry deaktiviert (lokale Entwicklung) - siehe main.py.
    sentry_dsn: str = ""


settings = Settings()

for _dir in (
    settings.photos_incoming_dir,
    settings.photos_processed_dir,
    settings.photos_normalized_dir,
):
    _dir.mkdir(parents=True, exist_ok=True)
