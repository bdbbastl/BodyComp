# Produktions-Hosting (Stufe 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SQLite → Postgres, lokales Filesystem → dauerhaftes Object-Storage
(Cloudflare R2), ein einzelner Railway-Service liefert Backend+Frontend
aus, Bild-Kompression beim Upload, Error-Tracking (Sentry), sauberes
Deploy-Gate über Tests.

**Architecture:** Siehe `docs/superpowers/specs/2026-08-15-production-hosting-design.md`
für den vollen Kontext. **Eine Architektur-Präzisierung gegenüber der
Spec:** Die Spec beschreibt eine `StorageBackend`-Abstraktion mit
`save/url_for/delete` plus presigned URLs. Bei der Umsetzungsplanung
zeigt sich, dass ein **lokaler Sync-Cache** (`services/storage_sync.py`
mit `ensure_local(rel_path)`/`push(rel_path)`/`delete_remote(rel_path)`)
dasselbe Ziel (dauerhafter Speicher über Neustarts hinweg, R2 als
Quelle der Wahrheit) mit erheblich weniger Umbau erreicht: die
komplette bestehende Bildverarbeitung (`pose_normalization.py`,
`thumbnails.py`, `heic.py`, `exif.py`) arbeitet unverändert mit echten
lokalen `Path`-Objekten weiter (MediaPipe/OpenCV/Pillow brauchen ohnehin
lokale Dateien) - nur an den Lese-/Schreib-/Lösch-Rändern (in
`folder_sync.py`/`routers/photos.py`/`routers/public_checkin.py`) wird
je eine Zeile ergänzt, die vor dem Lesen synct bzw. nach dem Schreiben
hochlädt. Kein Schema-Umbau (`PhotoOut` bleibt unverändert), kein
Frontend-Umbau (`mediaUrl()`/`/media`-Route bleiben bestehen, nur die
`/media`-Route wird von `StaticFiles` auf einen eigenen Handler
umgestellt, der vor dem Ausliefern synct). Presigned URLs direkt vom
Browser gegen R2 bleiben eine denkbare spätere Optimierung, sind aber
für die aktuelle Größenordnung nicht nötig.

**Tech Stack:** FastAPI/SQLAlchemy/Alembic, Postgres, Cloudflare R2
(`boto3`, S3-kompatibel), Railway (Nixpacks), Sentry.

---

## Part 1 — Datenbank: SQLite → Postgres

### Task 1: Dialekt-bewusste Konfiguration

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/core/database.py`

- [ ] **Step 1: `database_url` liest `DATABASE_URL`, fällt auf SQLite zurück**

In `backend/app/core/config.py`, `database_url`-Property ersetzen:

```python
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
```

- [ ] **Step 2: `psycopg` als Dependency ergänzen**

In `backend/requirements.txt`, nach `sqlalchemy>=2.0.35` ergänzen:

```
psycopg[binary]>=3.2.3
```

Run: `cd backend && .venv/Scripts/pip install "psycopg[binary]>=3.2.3"`

- [ ] **Step 3: `PRAGMA foreign_keys=ON`-Listener nur für SQLite registrieren**

In `backend/app/core/database.py`:

```python
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
```

- [ ] **Step 4: Backend-Suite laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: alle grün (lokale Tests laufen weiterhin gegen SQLite, `DATABASE_URL` ist lokal nicht gesetzt).

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/config.py backend/app/core/database.py backend/requirements.txt
git commit -m "feat: read DATABASE_URL for Postgres, make SQLite FK pragma dialect-aware"
```

---

### Task 2: Alembic-Setup + Baseline-Migration

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/0001_initial_schema.py`

- [ ] **Step 1: Alembic initialisieren**

Run: `cd backend && .venv/Scripts/alembic init alembic`

Das legt `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako` und
den leeren `alembic/versions/`-Ordner an.

- [ ] **Step 2: `alembic.ini` auf die App-Konfiguration verweisen**

In `backend/alembic.ini`, die Zeile `sqlalchemy.url = driver://user:pass@localhost/dbname`
entfernen (wird stattdessen dynamisch in `env.py` gesetzt, siehe Step 3)
- einfach die Zeile auskommentieren oder löschen.

- [ ] **Step 3: `alembic/env.py` an die App-Modelle/Konfiguration anbinden**

In `backend/alembic/env.py`, nach den bestehenden Imports ergänzen und
`target_metadata`/die URL-Auflösung anpassen:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.core.database import Base
# Alle Modelle importieren, damit sie bei Base.metadata registriert sind -
# analog zu app/models/__init__.py, hier explizit für Alembics Autogenerate.
from app.models import app_setting, user, client, email_token  # noqa: F401
from app.models import pose, day_log, photo, checkin_submission  # noqa: F401

target_metadata = Base.metadata


def get_url() -> str:
    return settings.database_url
```

In den bestehenden `run_migrations_offline()`/`run_migrations_online()`-
Funktionen: jedes Vorkommen von `config.get_main_option("sqlalchemy.url")`
durch `get_url()` ersetzen (2 Stellen).

- [ ] **Step 4: Baseline-Migration erzeugen**

Run: `cd backend && DATABASE_URL=postgresql+psycopg://user:pass@localhost/dummy .venv/Scripts/alembic revision --autogenerate -m "initial schema"`

Hinweis: dieser Befehl braucht eine ERREICHBARE Postgres-Instanz, gegen
die Alembic den aktuellen Modellstand vergleicht (Autogenerate). Lokal
am einfachsten über einen kurzlebigen Docker-Container:

```bash
docker run --rm -d --name bodycomp-alembic-tmp -e POSTGRES_PASSWORD=pw -p 5433:5432 postgres:16
# warten bis der Container bereit ist (paar Sekunden), dann:
cd backend && DATABASE_URL=postgresql+psycopg://postgres:pw@localhost:5433/postgres .venv/Scripts/alembic revision --autogenerate -m "initial schema"
docker stop bodycomp-alembic-tmp
```

Falls kein Docker verfügbar ist: die generierte Migrationsdatei
alternativ von Hand anhand der bestehenden Modelle
(`backend/app/models/*.py`) schreiben - sie muss exakt den aktuellen
Stand aller Tabellen/Spalten/Constraints/Indizes abbilden, wie er in
den `Mapped[...]`-Definitionen der Modelle steht (Client inkl. aller
Stufe-3-Felder, User, EmailToken, AppSetting, Pose, DayLog, Photo inkl.
`checkin_submission_id`, CheckinSubmission).

- [ ] **Step 5: Generierte Migration prüfen**

Öffne die neu entstandene Datei in `backend/alembic/versions/` und
prüfe: enthält sie ALLE Tabellen (users, clients, email_tokens,
app_settings, poses, day_logs, photos, checkin_submissions) mit allen
Spalten, Foreign Keys (inkl. `ondelete`-Verhalten) und Indizes? Benenne
die Datei zu `0001_initial_schema.py` um (bzw. passe `down_revision`
entsprechend an, falls Alembic einen Hash-Namen vergeben hat).

- [ ] **Step 6: Commit**

```bash
git add backend/alembic.ini backend/alembic/
git commit -m "feat: set up Alembic with initial schema baseline migration"
```

---

### Task 3: Migrations-Ausführung beim Start + Legacy-Migrationen auf SQLite beschränken

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Lightweight-Migrationen und Legacy-Fix nur für SQLite laufen lassen**

In `backend/app/main.py`, `lifespan()` anpassen - `run_lightweight_migrations`
und `fix_users_password_hash_nullable` sind beide SQLite-spezifische
Workarounds (rohe `ALTER TABLE`, `PRAGMA table_info`) und für Postgres
weder nötig (Alembic übernimmt das) noch kompatibel:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        # Nur für lokale SQLite-Entwicklung - Produktion (Postgres) nutzt
        # stattdessen echte Alembic-Migrationen (siehe alembic/), die als
        # Teil des Railway-Start-Kommandos laufen (siehe Task 11).
        run_lightweight_migrations(engine)
        fix_users_password_hash_nullable(engine)
    scheduler = None if "PYTEST_CURRENT_TEST" in os.environ else start_scheduler()
    yield
    if scheduler is not None:
        scheduler.shutdown()
```

- [ ] **Step 2: Backend-Suite laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: alle grün (Tests laufen gegen SQLite, `engine.dialect.name == "sqlite"` ist dort `True`).

- [ ] **Step 3: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: run legacy SQLite migrations only on SQLite, Postgres uses Alembic"
```

---

## Part 2 — Dauerhafter Objekt-Speicher (Cloudflare R2) über lokalen Sync-Cache

### Task 4: `storage_sync.py` - Sync-Grundfunktionen + R2-Client

**Files:**
- Create: `backend/app/services/storage_sync.py`
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/test_storage_sync.py`

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_storage_sync.py
"""
storage_sync arbeitet gegen echte lokale Dateien im settings.data_dir -
die R2-Anbindung selbst wird mit einem Fake-Client getestet (kein echter
Netzwerkzugriff in Tests), die Kern-Logik (wann wird gesynct, wann nicht)
ist aber dieselbe wie im echten Betrieb.
"""
from pathlib import Path

import pytest

from app.services import storage_sync


class FakeR2Client:
    """Simuliert boto3's S3-Client-Interface, soweit storage_sync es nutzt."""

    def __init__(self):
        self.uploaded: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def upload_file(self, local_path, bucket, key):
        self.uploaded[key] = Path(local_path).read_bytes()

    def download_file(self, bucket, key, local_path):
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        Path(local_path).write_bytes(self.uploaded[key])

    def delete_object(self, Bucket, Key):
        self.deleted.append(Key)
        self.uploaded.pop(Key, None)

    def head_object(self, Bucket, Key):
        if Key not in self.uploaded:
            from botocore.exceptions import ClientError
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")


@pytest.fixture()
def fake_r2(monkeypatch, tmp_path):
    fake_client = FakeR2Client()
    monkeypatch.setattr(storage_sync, "_r2_client", lambda: fake_client)
    monkeypatch.setattr(storage_sync.settings, "data_dir", tmp_path)
    monkeypatch.setattr(storage_sync.settings, "storage_backend", "r2")
    monkeypatch.setattr(storage_sync.settings, "r2_bucket", "test-bucket")
    return fake_client


def test_push_uploads_local_file_to_r2(fake_r2, tmp_path):
    local_file = tmp_path / "photos_processed" / "1" / "a.jpg"
    local_file.parent.mkdir(parents=True)
    local_file.write_bytes(b"fake-jpeg-bytes")

    storage_sync.push("photos_processed/1/a.jpg")

    assert fake_r2.uploaded["photos_processed/1/a.jpg"] == b"fake-jpeg-bytes"


def test_push_is_noop_when_backend_is_local(monkeypatch, tmp_path):
    monkeypatch.setattr(storage_sync.settings, "storage_backend", "local")
    # Kein Fake-Client gesetzt - würde eine echte Netzwerkanfrage auslösen
    # und crashen, wenn push() ihn fälschlich aufrufen würde.
    storage_sync.push("irrelevant/path.jpg")  # darf nicht werfen


def test_ensure_local_downloads_missing_file_from_r2(fake_r2, tmp_path):
    fake_r2.uploaded["photos_processed/1/a.jpg"] = b"from-r2"
    local_file = tmp_path / "photos_processed" / "1" / "a.jpg"
    assert not local_file.exists()

    storage_sync.ensure_local("photos_processed/1/a.jpg")

    assert local_file.exists()
    assert local_file.read_bytes() == b"from-r2"


def test_ensure_local_skips_download_if_already_present_locally(fake_r2, tmp_path):
    local_file = tmp_path / "photos_processed" / "1" / "a.jpg"
    local_file.parent.mkdir(parents=True)
    local_file.write_bytes(b"already-here")

    storage_sync.ensure_local("photos_processed/1/a.jpg")

    assert local_file.read_bytes() == b"already-here"
    assert "photos_processed/1/a.jpg" not in fake_r2.uploaded  # nie hochgeladen, nur lokal geprüft


def test_delete_remote_removes_from_r2(fake_r2):
    fake_r2.uploaded["photos_processed/1/a.jpg"] = b"data"

    storage_sync.delete_remote("photos_processed/1/a.jpg")

    assert "photos_processed/1/a.jpg" not in fake_r2.uploaded
    assert "photos_processed/1/a.jpg" in fake_r2.deleted
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_storage_sync.py -v`
Expected: FAIL (`ModuleNotFoundError: app.services.storage_sync`).

- [ ] **Step 3: `boto3` als Dependency ergänzen**

In `backend/requirements.txt`:

```
boto3>=1.35.0
```

Run: `cd backend && .venv/Scripts/pip install "boto3>=1.35.0"`

- [ ] **Step 4: Konfiguration ergänzen**

In `backend/app/core/config.py`, in der `Settings`-Klasse ergänzen:

```python
    # "local" (Default, lokale Entwicklung) oder "r2" (Produktion) - siehe
    # services/storage_sync.py.
    storage_backend: str = "local"
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = "bodycomp"
```

- [ ] **Step 5: `storage_sync.py` implementieren**

```python
# backend/app/services/storage_sync.py
"""
Dauerhafter Objekt-Speicher (Cloudflare R2) über einen lokalen Sync-
Cache - siehe Design-Spec Abschnitt "Datei-Speicherung" und die
Architektur-Präzisierung im Implementierungsplan. `settings.data_dir`
bleibt in BEIDEN Betriebsmodi das lokale Arbeitsverzeichnis, in dem die
bestehende Bildverarbeitung (pose_normalization.py, thumbnails.py,
heic.py) unverändert mit echten Path-Objekten arbeitet:

- storage_backend="local" (Standard, lokale Entwicklung): push/
  ensure_local/delete_remote sind No-Ops, data_dir ist die einzige
  Quelle der Wahrheit, wie bisher.
- storage_backend="r2" (Produktion): data_dir wird zum FLÜCHTIGEN
  lokalen Cache (Railways Plattenspeicher wird bei jedem Redeploy/
  Neustart geleert) - R2 ist die eigentliche Quelle der Wahrheit.
  push() lädt eine gerade geschriebene Datei sofort nach R2 hoch,
  ensure_local() holt eine (auf dieser Instanz noch nicht gecachte)
  Datei bei Bedarf von R2, delete_remote() räumt in R2 mit auf.
"""
import logging

from botocore.exceptions import ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)

_client = None


def _r2_client():
    """Lazy erzeugter, gecachter boto3-S3-Client gegen den R2-Endpoint.
    Als eigene, patchbare Funktion (statt Modul-Level-Konstante), damit
    Tests sie einfach durch einen Fake ersetzen können."""
    global _client
    if _client is None:
        import boto3

        _client = boto3.client(
            "s3",
            endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name="auto",
        )
    return _client


def push(rel_path: str) -> None:
    """Lädt settings.data_dir/rel_path nach R2 hoch. No-Op im lokalen
    Modus. Aufrufer: direkt nachdem eine Datei fertig geschrieben wurde
    (Upload, Thumbnail, Normalisierung, Verschieben)."""
    if settings.storage_backend != "r2":
        return
    local_path = settings.data_dir / rel_path
    try:
        _r2_client().upload_file(str(local_path), settings.r2_bucket, rel_path)
    except Exception:
        logger.exception("R2-Upload fehlgeschlagen für %s", rel_path)
        raise


def ensure_local(rel_path: str) -> None:
    """Stellt sicher, dass settings.data_dir/rel_path lokal existiert -
    lädt bei Bedarf von R2 herunter. No-Op im lokalen Modus (und wenn
    die Datei bereits lokal vorhanden ist, z.B. auf derselben Instanz,
    die sie geschrieben hat). Aufrufer: direkt VOR jedem Lesezugriff auf
    eine potenziell noch nicht lokal gecachte Datei."""
    if settings.storage_backend != "r2":
        return
    local_path = settings.data_dir / rel_path
    if local_path.exists():
        return
    try:
        _r2_client().download_file(settings.r2_bucket, rel_path, str(local_path))
    except ClientError:
        # Datei existiert auch in R2 nicht (z.B. gelöscht/nie hochgeladen) -
        # der Aufrufer behandelt eine fehlende lokale Datei bereits heute
        # als normalen Zustand (z.B. `if not source.exists(): continue`).
        logger.warning("R2-Download fehlgeschlagen (existiert nicht?) für %s", rel_path)


def delete_remote(rel_path: str) -> None:
    """Löscht rel_path aus R2. No-Op im lokalen Modus. Aufrufer: überall
    dort, wo heute schon die lokale Datei gelöscht wird."""
    if settings.storage_backend != "r2":
        return
    try:
        _r2_client().delete_object(Bucket=settings.r2_bucket, Key=rel_path)
    except Exception:
        logger.exception("R2-Löschung fehlgeschlagen für %s", rel_path)
```

- [ ] **Step 6: Tests laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_storage_sync.py -v`
Expected: alle PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/storage_sync.py backend/app/core/config.py backend/requirements.txt backend/tests/test_storage_sync.py
git commit -m "feat: add R2 storage sync (ensure_local/push/delete_remote)"
```

---

### Task 5: Sync-Aufrufe in `folder_sync.py` verdrahten

**Files:**
- Modify: `backend/app/services/folder_sync.py`

- [ ] **Step 1: `push()` nach jedem Schreiben ergänzen**

In `backend/app/services/folder_sync.py`, `from app.services.storage_sync import push`
importieren. Dann an folgenden Stellen JEWEILS direkt nach dem
erfolgreichen Schreiben `push(<relativer_pfad>)` ergänzen:

- In `_backfill_missing_previews`: nach `photo.preview_path = preview_dest.relative_to(settings.data_dir).as_posix()`
  (innerhalb des `if generate_preview(file, preview_dest):`-Blocks) → `push(photo.preview_path)` ergänzen.
- In `sync_incoming_folder`, nach der Preview-Generierung (`if generate_preview(file, preview_dest): preview_rel_path = ...`)
  → `push(preview_rel_path)` ergänzen (innerhalb desselben `if`).
- In `sync_incoming_folder`, nach der Thumbnail-Generierung (`thumb_rel_path = (... if generate_thumbnail(...) else None)`)
  → direkt danach, nur wenn `thumb_rel_path is not None`: `push(thumb_rel_path)` ergänzen.
- In `sync_incoming_folder`, nach `db.add(photo)` / vor `new_photos.append(photo)`:
  das ORIGINAL selbst muss auch hochgeladen werden - `push(rel_path)` ergänzen (die Originaldatei
  liegt zu diesem Zeitpunkt bereits unverändert im incoming_dir, z.B. vom Browser-Upload).

- [ ] **Step 2: `ensure_local()` vor jedem Lesen ergänzen**

- In `_backfill_missing_previews`: vor `file = settings.data_dir / photo.original_path` bzw. vor
  `if not file.exists() or not is_heic(file):` → `from app.services.storage_sync import ensure_local`
  importieren, dann `ensure_local(photo.original_path)` VOR der `.exists()`-Prüfung ergänzen.
- In `sync_incoming_folder`: die Funktion scannt `incoming_dir.rglob("*")` (frisch hochgeladene/
  gedropte Dateien, die noch nicht in R2 liegen) - hier ist KEIN `ensure_local` nötig, diese Dateien
  existieren immer schon lokal (sie kommen ja gerade erst rein).

- [ ] **Step 3: Backend-Suite laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: alle grün (lokale Tests laufen mit `storage_backend="local"` per Default, `push`/`ensure_local` sind dort No-Ops).

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/folder_sync.py
git commit -m "feat: wire R2 sync into folder_sync (push on write, ensure_local on read)"
```

---

### Task 6: Sync-Aufrufe in `routers/photos.py` verdrahten

**Files:**
- Modify: `backend/app/routers/photos.py`

- [ ] **Step 1: Import ergänzen**

```python
from app.services.storage_sync import delete_remote, ensure_local, push
```

- [ ] **Step 2: `ensure_local()` vor jedem Lesen ergänzen**

An JEDER der folgenden Stellen (Zeilenangaben beziehen sich auf den
Stand vor diesem Task, exakte Zeilen können nach vorherigen Tasks leicht
abweichen - anhand des Codes/Kommentars identifizieren) direkt VOR dem
`settings.data_dir / ...`-Ausdruck `ensure_local(...)` mit demselben
relativen Pfad ergänzen:

- `renormalize_all` (~Zeile 136): vor `src = settings.data_dir / (photo.preview_path or photo.original_path)`
  → `ensure_local(photo.preview_path or photo.original_path)`.
- `backfill_thumbnails` (~Zeile 175): vor `source = settings.data_dir / (photo.preview_path or photo.original_path)`
  → `ensure_local(photo.preview_path or photo.original_path)`.
- `_assign_photo` (~Zeile 211): vor `src = settings.data_dir / photo.original_path`
  → `ensure_local(photo.original_path)`.
- `_assign_photo`, HEIC-Vorschau-Verschiebung (~Zeile 222): vor `preview_src = settings.data_dir / photo.preview_path`
  → `ensure_local(photo.preview_path)` (innerhalb des `if photo.preview_path:`-Blocks).
- `_assign_photo`, Thumbnail-Verschiebung (~Zeile 232): vor `thumb_src = settings.data_dir / photo.thumbnail_path`
  → `ensure_local(photo.thumbnail_path)` (innerhalb des `if photo.thumbnail_path:`-Blocks).
- `_assign_photo`, Normalisierungs-Quelle (~Zeile 254): vor `normalize_source = settings.data_dir / (photo.preview_path or photo.original_path)`
  → `ensure_local(photo.preview_path or photo.original_path)`.
- `_delete_photo_files` (~Zeile 321): direkt VOR der `for rel_path in (...)`-Schleife, INNERHALB der
  Schleife vor `file = settings.data_dir / rel_path` → `ensure_local(rel_path)` (nur wenn `rel_path` truthy, wie die bestehende `if not rel_path: continue`-Zeile es schon absichert).
- `change_photo_pose`, alte normalisierte Datei (~Zeile 404): vor `old_normalized = settings.data_dir / photo.normalized_path if photo.normalized_path else None`
  → wenn `photo.normalized_path`, `ensure_local(photo.normalized_path)` davor ergänzen.
- `change_photo_pose`, Normalisierungs-Quelle (~Zeile 409): vor `normalize_source = settings.data_dir / (photo.preview_path or photo.original_path)`
  → `ensure_local(photo.preview_path or photo.original_path)`.

- [ ] **Step 3: `push()` nach jedem Schreiben ergänzen**

- `upload_photos`: nach der Upload-Schleife (nach `saved_any = True`, also die hochgeladene Datei liegt
  jetzt in `incoming_dir`) → `push(dest.relative_to(settings.data_dir).as_posix())` direkt nach dem
  `with dest.open("wb") as f: shutil.copyfileobj(...)`-Block ergänzen.
- `renormalize_all`: nach `photo.normalized_path = result.normalized_path.relative_to(settings.data_dir).as_posix()`
  → `push(photo.normalized_path)`.
- `backfill_thumbnails`: nach `photo.thumbnail_path = dest.relative_to(settings.data_dir).as_posix()`
  → `push(photo.thumbnail_path)`.
- `_assign_photo`, Original verschieben (~Zeile 217): nach `photo.original_path = dest.relative_to(settings.data_dir).as_posix()`
  → `push(photo.original_path)`.
- `_assign_photo`, HEIC-Vorschau verschieben: nach `photo.preview_path = preview_dest.relative_to(settings.data_dir).as_posix()`
  → `push(photo.preview_path)`.
- `_assign_photo`, Thumbnail verschieben ODER neu generieren (beide Zweige, ~Zeile 236-241): nach jeweils
  `photo.thumbnail_path = ...` → `push(photo.thumbnail_path)`.
- `_assign_photo`, Normalisierung: nach `photo.normalized_path = result.normalized_path.relative_to(settings.data_dir).as_posix()`
  → `push(photo.normalized_path)`.
- `change_photo_pose`: nach `photo.normalized_path = result.normalized_path.relative_to(settings.data_dir).as_posix()`
  → `push(photo.normalized_path)`.

- [ ] **Step 4: `delete_remote()` beim Löschen ergänzen**

In `_delete_photo_files`, INNERHALB der `for rel_path in (...)`-Schleife, nach dem bestehenden
`if file.exists(): file.unlink()` → `delete_remote(rel_path)` ergänzen (außerhalb des `if
file.exists()`, da die Datei in R2 liegen kann, auch wenn der LOKALE Cache sie gerade nicht (mehr)
hat).

In `change_photo_pose`, nach `if old_normalized and old_normalized.exists(): old_normalized.unlink()`
→ zusätzlich `delete_remote(photo.normalized_path)` mit dem ALTEN (vor der Neuzuweisung gemerkten)
Pfad ergänzen - dafür VOR der Neuzuweisung von `photo.normalized_path` den alten relativen Pfad in
einer Variable sichern (z.B. `old_normalized_rel_path = photo.normalized_path`, analog zu `old_normalized`).

- [ ] **Step 5: Backend-Suite laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: alle grün.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/photos.py
git commit -m "feat: wire R2 sync into photos router (all read/write/delete sites)"
```

---

### Task 7: Sync-Aufrufe in `routers/public_checkin.py` verdrahten + `/media`-Route

**Files:**
- Modify: `backend/app/routers/public_checkin.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: `push()` nach dem Foto-Upload in `submit_checkin`**

In `backend/app/routers/public_checkin.py`, `from app.services.storage_sync import push`
importieren. Nach dem `with dest.open("wb") as f: shutil.copyfileobj(upload.file, f)`-Block
(innerhalb der Upload-Schleife) → `push(dest.relative_to(settings.data_dir).as_posix())` ergänzen -
direkt vor oder nach der bestehenden `written_paths.add(...)`-Zeile.

- [ ] **Step 2: `/media`-Route von `StaticFiles` auf eigenen, synchronisierenden Handler umstellen**

In `backend/app/main.py`: die bestehende Zeile

```python
app.mount("/media", StaticFiles(directory=settings.data_dir), name="media")
```

ersetzen durch einen eigenen Endpoint, der vor dem Ausliefern synct
(gleiche URL-Struktur, keine Frontend-Änderung nötig):

```python
from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.services.storage_sync import ensure_local


@app.get("/media/{rel_path:path}")
def serve_media(rel_path: str):
    ensure_local(rel_path)
    file_path = settings.data_dir / rel_path
    if not file_path.is_file():
        raise HTTPException(404, "Datei nicht gefunden")
    return FileResponse(file_path)
```

(Der `app.mount("/media", ...)`-Aufruf und der `StaticFiles`-Import werden entfernt/ersetzt.)

- [ ] **Step 3: Backend-Suite laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: alle grün.

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/public_checkin.py backend/app/main.py
git commit -m "feat: wire R2 sync into public checkin uploads, replace /media StaticFiles mount"
```

---

## Part 3 — Bild-Kompression beim Upload

### Task 8: Größen-/Qualitäts-Normalisierung in `sync_incoming_folder`

**Files:**
- Modify: `backend/app/services/folder_sync.py`
- Test: `backend/tests/test_folder_sync.py` (falls nicht vorhanden, neu anlegen)

- [ ] **Step 1: Failing test**

Prüfe zuerst, ob `backend/tests/test_folder_sync.py` bereits existiert
(`ls backend/tests/ | grep folder_sync`). Falls ja, den Test dort
ergänzen; falls nein, neu anlegen:

```python
# backend/tests/test_folder_sync.py (ergänzen falls Datei existiert)
from pathlib import Path

from PIL import Image

from app.services.folder_sync import sync_incoming_folder
from app.services.storage_paths import incoming_dir_for_client


def test_sync_compresses_large_incoming_photo(db_session, monkeypatch, tmp_path):
    from app.core.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    incoming_dir = incoming_dir_for_client(1)
    incoming_dir.mkdir(parents=True)

    # Großes Test-Bild (4000x3000, deutlich über der 2500px-Grenze).
    large_image_path = incoming_dir / "big.jpg"
    Image.new("RGB", (4000, 3000), color="red").save(large_image_path, "JPEG", quality=100)
    original_size = large_image_path.stat().st_size

    sync_incoming_folder(db_session, client_id=1)

    with Image.open(large_image_path) as img:
        assert max(img.size) <= 2500
    assert large_image_path.stat().st_size < original_size
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_folder_sync.py -k compress -v`
Expected: FAIL (Bild bleibt unverändert bei 4000x3000).

- [ ] **Step 3: Kompressions-Funktion implementieren**

In `backend/app/services/folder_sync.py`, `from PIL import Image, ImageOps`
zu den Imports ergänzen und folgende Funktion vor `sync_incoming_folder` einfügen:

```python
MAX_ORIGINAL_EDGE = 2500
ORIGINAL_JPEG_QUALITY = 85


def _compress_original_in_place(path: Path) -> None:
    """Verkleinert/rekomprimiert ein frisch eingegangenes Foto VOR der
    weiteren Verarbeitung (EXIF-Auslesung passiert vorher, siehe
    Aufrufer) - siehe Design-Spec Abschnitt "Kompression beim Upload".
    Handy-Fotos (oft 8-15 MB) schrumpfen so typischerweise auf wenige
    hundert KB. Bewusst NUR für normale JPEG/PNG-Originale - HEIC-Dateien
    behalten ihr Rohformat (die JPEG-Vorschau wird an anderer Stelle
    bereits als komprimierte Kopie erzeugt, siehe services/heic.py), und
    ein Fehlschlag (kaputte Datei) blockiert den restlichen Sync nicht."""
    try:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)  # Rotation dauerhaft einbrennen
            img = img.convert("RGB")
            width, height = img.size
            scale = MAX_ORIGINAL_EDGE / max(width, height)
            if scale < 1:
                img = img.resize(
                    (max(1, int(width * scale)), max(1, int(height * scale))), Image.LANCZOS
                )
            img.save(path, format="JPEG", quality=ORIGINAL_JPEG_QUALITY)
    except Exception:
        logger.warning("Konnte Foto nicht komprimieren, behalte Original: %s", path, exc_info=True)
```

`import logging` + `logger = logging.getLogger(__name__)` ergänzen, falls
noch nicht vorhanden.

- [ ] **Step 4: Aufruf in `sync_incoming_folder` einbauen**

In `sync_incoming_folder`, in der `for file in sorted(incoming_dir.rglob("*")):`-Schleife: direkt
NACH `taken_at = get_taken_at(file)` (EXIF muss VOR der Kompression gelesen werden, da
`save(..., format="JPEG")` die EXIF-Daten nicht zuverlässig erhält) und NUR für nicht-HEIC-Dateien
(`if not is_heic(file): _compress_original_in_place(file)`) ergänzen - HEIC-Originale bleiben
unangetastet (siehe Docstring oben), ihre bereits komprimierte JPEG-Vorschau übernimmt effektiv
denselben Zweck.

- [ ] **Step 5: Test laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_folder_sync.py -v`
Expected: PASS.

- [ ] **Step 6: Volle Backend-Suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: alle grün (bestehende Foto-Tests mit kleinen Test-Bildern bleiben unter der 2500px-Grenze,
unverändert).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/folder_sync.py backend/tests/test_folder_sync.py
git commit -m "feat: compress/resize photos on ingest (max 2500px, JPEG q85)"
```

---

## Part 4 — Single-Service-Deploy (FastAPI liefert Frontend mit aus)

### Task 9: FastAPI liefert gebautes Frontend aus

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: SPA-Fallback-Route + statische Assets ergänzen**

In `backend/app/main.py`, GANZ AM ENDE der Datei (nach allen `app.include_router(...)`-Aufrufen und
dem `/api/health`-Endpoint) ergänzen - muss zuletzt registriert werden, da es sonst als Fallback
sämtliche `/api/*`- und `/media/*`-Pfade "verschlucken" würde:

```python
_frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"

if _frontend_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=_frontend_dist / "assets"), name="frontend-assets")

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        """SPA-Fallback: jede nicht von einer API-/Media-Route abgedeckte
        URL liefert index.html aus - React Router übernimmt das clientseitige
        Routing (siehe frontend/src/App.tsx). Nur aktiv, wenn ein Frontend-
        Build vorhanden ist (lokale Entwicklung nutzt weiterhin den
        separaten Vite-Dev-Server auf :5173 und braucht diese Route nicht)."""
        return FileResponse(_frontend_dist / "index.html")
```

`from pathlib import Path` ist bereits über `app/core/config.py`-Importkette
nicht automatisch verfügbar - `Path` explizit in `main.py` importieren, falls
noch nicht vorhanden (`from pathlib import Path` zu den Imports ergänzen).

- [ ] **Step 2: CORS-Middleware auf Dev-Only beschränken**

In `backend/app/main.py`: die bestehende `CORSMiddleware`-Registrierung nur
noch lokal nötig, da Backend+Frontend jetzt denselben Origin teilen. Um
die App aber weiterhin fehlerfrei lokal mit getrennten Dev-Servern laufen zu
lassen, bleibt sie unverändert bestehen (keine Änderung nötig) - in Produktion
sind `allow_origins` schlicht wirkungslos (kein Cross-Origin-Request mehr nötig).

- [ ] **Step 3: Smoke-Test - Backend startet weiterhin sauber ohne Frontend-Build**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: alle grün (`frontend/dist` existiert im Test-/Dev-Kontext nicht,
`_frontend_dist.is_dir()` ist `False`, die Fallback-Route wird gar nicht erst registriert -
bestehendes Verhalten bleibt für lokale Entwicklung unangetastet).

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: serve built frontend from FastAPI with SPA fallback route"
```

---

### Task 10: Railway Build-/Start-Konfiguration

**Files:**
- Create: `railway.json` (Repo-Root)
- Create: `nixpacks.toml` (Repo-Root)

- [ ] **Step 1: `nixpacks.toml` - Build-Schritte inkl. Test-Gate**

```toml
# nixpacks.toml (Repo-Root)
[phases.setup]
nixPkgs = ["python312", "nodejs_20"]

[phases.install]
cmds = [
  "cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt",
  "cd frontend && npm ci",
]

[phases.build]
cmds = [
  "cd frontend && npm run build",
  # Tests als Deploy-Gate: schlägt einer der beiden Befehle fehl, bricht
  # der Build ab und es wird nichts Kaputtes deployed (siehe Design-Spec
  # Abschnitt "Testing als Deploy-Gate").
  "cd frontend && npx tsc --noEmit",
  "cd backend && .venv/bin/python -m pytest -q",
]

[start]
cmd = "cd backend && .venv/bin/alembic upgrade head && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $PORT"
```

- [ ] **Step 2: `railway.json` - Verweist auf die Nixpacks-Konfiguration**

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3
  }
}
```

- [ ] **Step 3: Lokale Plausibilitätsprüfung**

Da ein echter Railway-Build lokal nicht 1:1 nachstellbar ist, stattdessen
die einzelnen Befehle aus `nixpacks.toml` manuell der Reihe nach lokal
ausführen und bestätigen, dass jeder für sich erfolgreich durchläuft:

```bash
cd frontend && npm run build && npx tsc --noEmit
cd ../backend && .venv/Scripts/python -m pytest -q
```

Expected: beide Blöcke laufen fehlerfrei durch.

- [ ] **Step 4: Commit**

```bash
git add railway.json nixpacks.toml
git commit -m "feat: add Railway/Nixpacks build+deploy config with test gate"
```

---

## Part 5 — Error-Tracking (Sentry)

### Task 11: Sentry Backend-Integration

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Dependency + Konfiguration**

In `backend/requirements.txt`:

```
sentry-sdk[fastapi]>=2.17.0
```

Run: `cd backend && .venv/Scripts/pip install "sentry-sdk[fastapi]>=2.17.0"`

In `backend/app/core/config.py`, `Settings`-Klasse ergänzen:

```python
    # Leer = Sentry deaktiviert (lokale Entwicklung) - siehe main.py.
    sentry_dsn: str = ""
```

- [ ] **Step 2: Sentry vor App-Erzeugung initialisieren**

In `backend/app/main.py`, GANZ AM ANFANG der Datei (vor `app = FastAPI(...)`,
direkt nach den bestehenden Imports) ergänzen:

```python
if settings.sentry_dsn:
    import sentry_sdk

    sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.1, send_default_pii=False)
```

(`send_default_pii=False`, da die App Klienten-Namen/E-Mails verarbeitet -
keine personenbezogenen Daten standardmäßig an Sentry senden.)

- [ ] **Step 3: Smoke-Test**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: alle grün (`sentry_dsn` ist lokal leer, Sentry wird gar nicht erst initialisiert).

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py backend/app/core/config.py backend/requirements.txt
git commit -m "feat: add optional Sentry error tracking for backend"
```

---

### Task 12: Sentry Frontend-Integration

**Files:**
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/package.json`

- [ ] **Step 1: Dependency installieren**

Run: `cd frontend && npm install @sentry/react`

- [ ] **Step 2: Sentry beim App-Start initialisieren**

In `frontend/src/main.tsx`:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import * as Sentry from "@sentry/react";
import App from "./App";
import "./index.css";

// import.meta.env.VITE_SENTRY_DSN muss beim Build gesetzt sein (Vite
// exponiert nur mit VITE_-Präfix versehene Env-Vars ans Frontend) - leer
// in lokaler Entwicklung, Sentry bleibt dann inaktiv.
if (import.meta.env.VITE_SENTRY_DSN) {
  Sentry.init({ dsn: import.meta.env.VITE_SENTRY_DSN, tracesSampleRate: 0.1 });
}

const queryClient = new QueryClient();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Sentry.ErrorBoundary fallback={<p>Etwas ist schiefgelaufen. Bitte Seite neu laden.</p>}>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </Sentry.ErrorBoundary>
  </React.StrictMode>
);
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/main.tsx frontend/package.json frontend/package-lock.json
git commit -m "feat: add optional Sentry error tracking for frontend"
```

---

## Part 6 — Dokumentation (manuelle Schritte)

### Task 13: README-Abschnitt für Produktions-Setup

**Files:**
- Modify: `README.md` (oder neu anlegen, falls nicht vorhanden - vorher prüfen)

- [ ] **Step 1: Bestehende README prüfen**

Run: `cat README.md` (bzw. `ls *.md` falls der Dateiname abweicht) - prüfen, ob bereits ein
Setup-Abschnitt existiert, an den angeknüpft werden kann.

- [ ] **Step 2: Abschnitt "Produktions-Deployment (Stufe 3)" ergänzen**

Am Ende der README (oder in einer neuen `docs/deployment.md`, falls die
README bereits sehr lang ist) folgenden Abschnitt ergänzen - dies sind
ausschließlich manuelle, kontoseitige Schritte, die der Nutzer selbst
durchführen muss (kein Code):

```markdown
## Produktions-Deployment (Stufe 3)

### Einmaliges Setup

1. **Railway-Projekt anlegen**, GitHub-Repo verbinden (Railway-GitHub-App
   braucht Zugriff auf private Repos - unter GitHub → Settings →
   Applications → Railway → Repository access prüfen/erweitern, falls
   das Repo dafür public gestellt werden musste).
2. **Postgres-Plugin** im Railway-Projekt hinzufügen - setzt `DATABASE_URL`
   automatisch als Umgebungsvariable für den App-Service.
3. **Tägliche Backups** für die Postgres-Instanz in den Railway-Plugin-
   Einstellungen aktivieren.
4. **Cloudflare R2 Bucket** anlegen (Name muss zu `R2_BUCKET` unten passen),
   API-Token mit Read/Write-Berechtigung erzeugen.
5. Folgende **Umgebungsvariablen** in Railway setzen (App-Service, nicht
   das Postgres-Plugin):
   - `BODYCOMP_SESSION_SECRET_KEY` (langer, zufälliger String)
   - `BODYCOMP_GOOGLE_CLIENT_ID`, `BODYCOMP_GOOGLE_CLIENT_SECRET`,
     `BODYCOMP_GOOGLE_REDIRECT_URI` (auf die Railway-Domain anpassen)
   - `BODYCOMP_RESEND_API_KEY`, `BODYCOMP_EMAIL_FROM_ADDRESS`
   - `BODYCOMP_FRONTEND_BASE_URL` (die Railway-App-URL selbst)
   - `GEMINI_API_KEY`
   - `BODYCOMP_STORAGE_BACKEND=r2`
   - `BODYCOMP_R2_ACCOUNT_ID`, `BODYCOMP_R2_ACCESS_KEY_ID`,
     `BODYCOMP_R2_SECRET_ACCESS_KEY`, `BODYCOMP_R2_BUCKET`
   - `BODYCOMP_SENTRY_DSN` (Backend-Fehler-Tracking)
   - `VITE_SENTRY_DSN` (Frontend-Fehler-Tracking, MUSS als Build-Zeit-
     Variable gesetzt sein, nicht nur zur Laufzeit - Vite bettet sie beim
     `npm run build` fest in den JS-Bundle ein)
6. **Uptime-Monitoring** einrichten: bei einem Dienst wie UptimeRobot
   (kostenlos) einen HTTP-Monitor auf `https://<deine-railway-domain>/api/health`
   anlegen, Intervall z.B. 5 Minuten, E-Mail-Alarm bei Ausfall.

### Laufender Betrieb

Jeder Push auf `main` (z.B. per `git merge dev` gefolgt von `git push`)
löst automatisch ein neues Deployment aus. Der Build bricht ab (kein
Deploy passiert), wenn Backend-Tests oder der Frontend-Typecheck fehlschlagen.
```

- [ ] **Step 3: Commit**

```bash
git add README.md  # oder docs/deployment.md, je nachdem was in Step 1 gewählt wurde
git commit -m "docs: add production deployment setup guide"
```

---

## Abschließende Verifikation

- [ ] Volle Backend-Suite: `cd backend && .venv/Scripts/python -m pytest -v` — alle grün (weiterhin gegen lokales SQLite).
- [ ] Frontend-Typecheck + Build: `cd frontend && npx tsc --noEmit && npm run build` — keine Fehler, `frontend/dist/` entsteht.
- [ ] Backend startet lokal weiterhin fehlerfrei mit `DATABASE_URL` NICHT gesetzt (SQLite-Fallback) und MIT gesetzt gegen eine lokale/temporäre Postgres-Instanz (z.B. via Docker) — `alembic upgrade head` läuft dagegen fehlerfrei durch.
- [ ] Bestätigen, dass jeder Schreib-/Lese-/Lösch-Aufruf auf eine Foto-Datei in `folder_sync.py`/`routers/photos.py`/`routers/public_checkin.py` von einem passenden `push`/`ensure_local`/`delete_remote`-Aufruf begleitet wird (Grep nach `settings.data_dir /` und gegen die Task-5/6/7-Listen abgleichen).
- [ ] Manueller Deploy-Test: Repo auf `main` pushen (nach Merge von `dev`), Railway-Build beobachten — muss ohne den eingangs aufgetretenen "Railpack could not determine how to build"-Fehler durchlaufen.
