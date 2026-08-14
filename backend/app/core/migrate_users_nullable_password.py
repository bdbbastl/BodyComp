"""
Einmalige Schema-Reparatur: die reale `users`-Tabelle wurde ursprünglich
(Stufe 1) mit `password_hash VARCHAR(255) NOT NULL` angelegt - als
Inline-Spalten-Constraint, den SQLite per ALTER TABLE nicht lockern kann.
Stufe 2 (Google OAuth) braucht aber `password_hash IS NULL` für rein über
Google registrierte Accounts. `run_lightweight_migrations` kann neue
Spalten nachtragen, aber keine bestehende NOT-NULL-Constraint entfernen -
das erledigt diese Datei per Tabellen-Rebuild (SQLite-Standardverfahren),
nach demselben Muster wie zuvor bei den legacy UNIQUE-Constraints auf
poses/day_logs (siehe Git-Historie).

Nebenbei behebt das auch, dass `google_id` bisher OHNE Unique-Index in
der realen DB existierte (nur per ALTER TABLE ADD COLUMN nachgetragen,
ohne den `unique=True` aus dem Model nachzubilden).

Läuft bei JEDEM Start (idempotent, No-Op sobald die Spalte schon
nullable ist und der Index existiert) - nicht an die "kein User
existiert"-Bedingung gekoppelt, weil es eine reine Schema-Reparatur ist,
unabhängig von Nutzerdaten.
"""
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def _sqlite_file_path(engine: Engine) -> Path | None:
    url = engine.url
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    return Path(url.database)


def _users_password_hash_is_nullable(engine: Engine) -> bool:
    inspector = inspect(engine)
    for col in inspector.get_columns("users"):
        if col["name"] == "password_hash":
            return bool(col["nullable"])
    return True  # Spalte existiert nicht (sollte nicht passieren) - kein Fixbedarf


def _users_has_google_id_unique_index(engine: Engine) -> bool:
    inspector = inspect(engine)
    for idx in inspector.get_indexes("users"):
        if idx.get("unique") and idx.get("column_names") == ["google_id"]:
            return True
    return False


def fix_users_password_hash_nullable(engine: Engine) -> None:
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return  # Frisch angelegte DB - create_all() hat das Schema schon korrekt.

    needs_fix = not _users_password_hash_is_nullable(engine) or not _users_has_google_id_unique_index(engine)
    if not needs_fix:
        return

    db_path = _sqlite_file_path(engine)
    if db_path is not None and db_path.exists():
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = db_path.with_name(f"{db_path.name}.pre-users-nullable-fix-{timestamp}")
        shutil.copy2(db_path, backup_path)

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS users_new"))
        conn.execute(text(
            "CREATE TABLE users_new ("
            "id INTEGER NOT NULL, "
            "email VARCHAR(255) NOT NULL, "
            "password_hash VARCHAR(255), "
            "display_name VARCHAR(100) NOT NULL, "
            "account_type VARCHAR(6) NOT NULL, "
            "created_at DATETIME NOT NULL, "
            "google_id VARCHAR(255), "
            "email_verified_at DATETIME, "
            "privacy_accepted_at DATETIME, "
            "sessions_invalidated_at DATETIME, "
            "PRIMARY KEY (id))"
        ))
        conn.execute(text(
            "INSERT INTO users_new ("
            "id, email, password_hash, display_name, account_type, created_at, "
            "google_id, email_verified_at, privacy_accepted_at, sessions_invalidated_at"
            ") SELECT "
            "id, email, password_hash, display_name, account_type, created_at, "
            "google_id, email_verified_at, privacy_accepted_at, sessions_invalidated_at "
            "FROM users"
        ))
        conn.execute(text("DROP TABLE users"))
        conn.execute(text("ALTER TABLE users_new RENAME TO users"))
        conn.execute(text("CREATE UNIQUE INDEX ix_users_email ON users (email)"))
        conn.execute(text("CREATE UNIQUE INDEX ix_users_google_id ON users (google_id)"))
