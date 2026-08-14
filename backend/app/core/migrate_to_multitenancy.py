"""
Einmaliges Migrationsscript: verschiebt die bestehenden Single-Tenant-
Daten (Poses/DayLogs/Photos ohne client_id) in einen neuen Client "Mein
Profil", der einem neu angelegten Account gehört - siehe Design-Spec
Abschnitt "Migration des bestehenden Datenbestands".

Wird von main.py's lifespan bei JEDEM Start aufgerufen, ist aber ein
No-Op, sobald mindestens ein User existiert (Erkennungsmerkmal laut
Spec) - so kann es gefahrlos öfter aufgerufen werden, ohne Daten
doppelt zu migrieren.

Bewegt zusätzlich die betroffenen Dateien auf der Platte in die neue
client-gescopte Ordnerstruktur (siehe services/storage_paths.py) und
aktualisiert die in der DB gespeicherten Pfade entsprechend.
"""
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.client import Client
from app.models.day_log import DayLog
from app.models.photo import Photo
from app.models.pose import Pose
from app.models.user import AccountType, User
from app.services.account import create_account
from app.services.storage_paths import processed_dir_for_client_date


def _move_file_into_client_folder(rel_path: str | None, client_id: int) -> str | None:
    """Verschiebt eine einzelne Datei (original/preview/thumbnail/
    normalized) in den client-gescopten Ordner, behält den restlichen
    Pfad (Datum, Dateiname) bei. Gibt den neuen relativen Pfad zurück,
    oder den unveränderten Wert, wenn die Datei nicht existiert (defensiv
    - eine fehlende Datei blockiert die Migration nicht)."""
    if not rel_path:
        return rel_path

    source = settings.data_dir / rel_path
    if not source.exists():
        return rel_path

    parts = Path(rel_path).parts  # z.B. ("photos_processed", "2026-01-01", "foo.jpg")
    if parts[0] == "photos_processed" and len(parts) >= 3:
        date_str = parts[1]
        filename = Path(*parts[2:])
        dest_dir = processed_dir_for_client_date(client_id, date_str)
    elif parts[0] == "photos_normalized" and len(parts) >= 3:
        pose_id_str = parts[1]
        filename = Path(*parts[2:])
        dest_dir = settings.photos_normalized_dir / str(client_id) / pose_id_str
    elif parts[0] == "photos_incoming" and len(parts) >= 2:
        filename = Path(*parts[1:])
        dest_dir = settings.photos_incoming_dir / str(client_id)
    else:
        return rel_path  # unbekanntes Layout - unverändert lassen

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    shutil.move(str(source), str(dest))
    return dest.relative_to(settings.data_dir).as_posix()


def _app_settings_has_legacy_schema(conn: Connection) -> bool:
    """True, wenn `app_settings` noch den alten Einzel-Spalten-PK auf
    `key` allein hat (Stand vor Task 10), statt des aktuellen
    Composite-PK `(owner_id, key)` (siehe app/models/app_setting.py).
    Erkennung anhand des tatsächlichen Primary-Key-Constraints in der
    DB - nicht anhand von Datenzuständen, analog zu
    migrate_legacy_unique_constraints.py."""
    inspector = inspect(conn)
    pk_columns = set(inspector.get_pk_constraint("app_settings").get("constrained_columns") or [])
    return "owner_id" not in pk_columns


def _rebuild_app_settings_table(conn: Connection, owner_id: int) -> None:
    """Baut `app_settings` von Einzel-PK (`key`) auf Composite-PK
    (`owner_id`, `key`) um - gleiches resumable Rebuild-Verfahren wie
    `_rebuild_poses_table`/`_rebuild_day_logs_table` in
    migrate_legacy_unique_constraints.py (SQLite kann eine bestehende
    PRIMARY KEY-Definition nicht per ALTER TABLE ändern). Jede
    bestehende Zeile gehört dem einzigen Account, der vor dieser
    Migration existierte."""
    conn.execute(text("DROP TABLE IF EXISTS app_settings_new"))
    conn.execute(text(
        "CREATE TABLE app_settings_new ("
        "owner_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE, "
        "\"key\" VARCHAR(100) NOT NULL, "
        "value VARCHAR(2000), "
        "PRIMARY KEY (owner_id, \"key\"))"
    ))
    conn.execute(
        text(
            "INSERT INTO app_settings_new (owner_id, \"key\", value) "
            "SELECT :owner_id, \"key\", value FROM app_settings"
        ),
        {"owner_id": owner_id},
    )
    conn.execute(text("DROP TABLE app_settings"))
    conn.execute(text("ALTER TABLE app_settings_new RENAME TO app_settings"))


def _app_settings_backup_path(db_path: Path) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return db_path.with_name(f"{db_path.name}.pre-app-settings-fix-{ts}")


def _sqlite_file_path(engine: Engine) -> Path | None:
    """Siehe gleichnamige Funktion in migrate_legacy_unique_constraints.py
    - Datei-Backup ist nur bei echten Datei-SQLite-DBs möglich/nötig,
    nicht bei `:memory:` (Tests)."""
    url = engine.url
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    return Path(url.database)


def _fix_app_settings_schema(engine: Engine, owner_id: int) -> None:
    """Repariert eine `app_settings`-Tabelle mit dem alten
    Einzel-Spalten-PK auf `key`, indem sie auf den aktuellen
    Composite-PK `(owner_id, key)` umgebaut wird und bestehende Zeilen
    dem übergebenen Account zugeordnet werden (siehe Modul-/Task-Doku).
    Sicherer No-Op, wenn `app_settings` noch gar nicht existiert (ganz
    frische Installation vor dem ersten `create_all()`) oder bereits
    das korrekte Composite-PK-Schema hat (frische Installation oder
    bereits reparierte DB)."""
    inspector = inspect(engine)
    if "app_settings" not in inspector.get_table_names():
        return

    db_file = _sqlite_file_path(engine)

    with engine.begin() as conn:
        if not _app_settings_has_legacy_schema(conn):
            return
        if db_file is not None and db_file.exists():
            shutil.copy2(db_file, _app_settings_backup_path(db_file))
        _rebuild_app_settings_table(conn, owner_id)


def migrate_to_multitenancy(
    db: Session, *, email: str, password: str, display_name: str
) -> None:
    engine = db.get_bind()
    user_count = db.query(User).count()

    if user_count > 0:
        # Schon migriert (oder frische Installation ohne Altdaten). Ein
        # bereits existierender User verhindert die eigentliche
        # Daten-Migration hier - ABER `app_settings` kann trotzdem noch
        # das alte Einzel-PK-Schema haben, falls dieser Fix erst in
        # einem SPÄTEREN Deploy als die ursprüngliche
        # migrate_to_multitenancy()-Migration dazukam (genau der reale
        # Zustand dieser Worktree-DB: User "Basti" existiert bereits,
        # `app_settings` wurde aber nie umgebaut). Bei genau einem
        # existierenden User reparieren wir das hier nachträglich, mit
        # dessen id als owner_id. Bei mehreren Usern ist unklar, wem
        # bestehende Legacy-Zeilen gehören sollen - dann bewusst nichts
        # tun (sollte im Ein-Account-POC nicht vorkommen).
        if user_count == 1:
            existing_user = db.query(User).first()
            _fix_app_settings_schema(engine, existing_user.id)
        return

    user = create_account(
        db, email=email, password=password, display_name=display_name
    )
    # create_account legt bereits EINEN Client namens display_name an
    # (siehe services/account.py) - für die Migration bestehender Daten
    # überschreiben wir dessen Namen auf "Mein Profil", statt einen
    # zweiten Client anzulegen.
    client_row = db.query(Client).filter(Client.owner_id == user.id).first()
    client_row.name = "Mein Profil"

    user.account_type = AccountType.COACH
    db.commit()

    poses = db.query(Pose).filter(Pose.client_id.is_(None)).all()
    for pose in poses:
        pose.client_id = client_row.id

    day_logs = db.query(DayLog).filter(DayLog.client_id.is_(None)).all()
    for day_log in day_logs:
        day_log.client_id = client_row.id

    photos = db.query(Photo).filter(Photo.client_id.is_(None)).all()
    for photo in photos:
        photo.client_id = client_row.id
        photo.original_path = _move_file_into_client_folder(photo.original_path, client_row.id)
        photo.preview_path = _move_file_into_client_folder(photo.preview_path, client_row.id)
        photo.thumbnail_path = _move_file_into_client_folder(photo.thumbnail_path, client_row.id)
        photo.normalized_path = _move_file_into_client_folder(photo.normalized_path, client_row.id)

    db.commit()

    # app_settings existiert auf einer ECHTEN Alt-DB bereits vor dieser
    # Migration (Einzel-PK auf `key`) - jetzt, wo der Account feststeht,
    # können bestehende Zeilen ihm zugeordnet werden (siehe
    # _fix_app_settings_schema-Docstring). Auf einer frischen Installation
    # ohne Altdaten ist das ein No-Op (Tabelle existiert entweder noch
    # nicht, oder create_all() hat sie von Anfang an mit dem korrekten
    # Composite-PK angelegt).
    _fix_app_settings_schema(engine, user.id)
