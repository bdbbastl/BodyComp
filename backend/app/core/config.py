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
        return f"sqlite:///{self.db_path.as_posix()}"

    # Erlaubte Dateiendungen beim Ordner-Sync
    allowed_extensions: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".heic")

    # Signiert die Session-Cookies (siehe services/auth.py). In Produktion
    # per BODYCOMP_SESSION_SECRET_KEY überschreiben - der Default ist nur
    # fürs lokale Dev-Setup gedacht.
    session_secret_key: str = "dev-only-insecure-secret-change-me"

    # Startpasswort für den einmalig migrierten Coach-Account (siehe
    # core/migrate_to_multitenancy.py). NICHT im Repo im Klartext - wird
    # über backend/.env gesetzt (BODYCOMP_MIGRATION_SEED_PASSWORD), nicht
    # committed (siehe .gitignore).
    migration_seed_password: str = "changeme-set-in-dotenv"


settings = Settings()

for _dir in (
    settings.photos_incoming_dir,
    settings.photos_processed_dir,
    settings.photos_normalized_dir,
):
    _dir.mkdir(parents=True, exist_ok=True)
