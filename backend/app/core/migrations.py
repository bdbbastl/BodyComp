"""
Sehr leichtgewichtige Schema-Migration für den POC.

`Base.metadata.create_all()` legt fehlende TABELLEN an, ändert aber nie
Spalten einer bereits existierenden Tabelle. Für neue nullable Spalten an
bestehenden Tabellen reicht hier ein simples "ALTER TABLE ... ADD COLUMN",
statt gleich Alembic aufzusetzen. Für die spätere Cloud-Version sollte das
durch echte Alembic-Migrationen ersetzt werden (siehe README).

Hinweis Mandantenfähigkeit: SQLite kann per ALTER TABLE keine UNIQUE-
Constraints nachrüsten oder ändern (Pose.name/DayLog.date wurden von
global-unique auf unique-pro-Client geändert) - das erledigt stattdessen
das einmalige Migrationsscript (app/core/migrate_to_multitenancy.py), das
diese Tabellen bei Bedarf komplett neu aufbaut. Diese Datei hier trägt nur
die rohe `client_id`-Spalte nach, ohne Constraint.
"""
import secrets

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

# (Tabelle, Spalte, SQL-Typ) - hier eintragen, wenn ein neues nullable
# Feld zu einem bestehenden Model hinzukommt.
_PENDING_COLUMNS: list[tuple[str, str, str]] = [
    ("photos", "preview_path", "VARCHAR(1000)"),
    ("photos", "thumbnail_path", "VARCHAR(1000)"),
    ("photos", "client_id", "INTEGER"),
    ("poses", "client_id", "INTEGER"),
    ("day_logs", "client_id", "INTEGER"),
    ("clients", "birth_date", "DATE"),
    ("users", "google_id", "VARCHAR(255)"),
    ("users", "email_verified_at", "DATETIME"),
    ("users", "privacy_accepted_at", "DATETIME"),
    ("users", "sessions_invalidated_at", "DATETIME"),
    ("clients", "checkin_token", "VARCHAR(64)"),
    ("clients", "coach_private_note", "TEXT"),
    ("clients", "email", "VARCHAR(255)"),
    ("clients", "checkin_reminder_days", "INTEGER"),
    ("clients", "last_reminder_sent_at", "DATETIME"),
    ("photos", "checkin_submission_id", "INTEGER"),
    ("users", "stripe_customer_id", "VARCHAR(255)"),
    ("users", "subscription_status", "VARCHAR(50)"),
    ("users", "subscription_tier", "VARCHAR(50)"),
    ("users", "trial_ends_at", "DATETIME"),
    ("users", "free_checkins_used", "INTEGER"),
    ("users", "onboarding_completed_at", "DATETIME"),
]


def _columns_now(conn, table: str) -> set[str]:
    """Spaltenliste über PRAGMA table_info auf DERSELBEN Connection/
    Transaktion wie die ALTER-TABLE-Statements - wichtig, weil ein
    `inspect(engine)`-Inspector intern eine EIGENE Connection nutzt und
    dadurch die in dieser Transaktion gerade erst hinzugefügten, noch
    nicht committeten Spalten nicht sieht. Damit hätte z.B. der
    checkin_token-Backfill unten (fälschlich "Spalte existiert nicht")
    beim ersten Lauf gegen eine echte, bestehende DB übersprungen -
    gefunden live beim Deploy dieser Migration."""
    return {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()}


def run_lightweight_migrations(engine: Engine) -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, column, sql_type in _PENDING_COLUMNS:
            if table not in existing_tables:
                continue  # Frisch angelegte DB - create_all() hat die Spalte schon.
            if column in _columns_now(conn, table):
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))

        if "users" in existing_tables:
            users_columns_now = _columns_now(conn, "users")
            if "email_verified_at" in users_columns_now and "password_hash" in users_columns_now:
                conn.execute(text(
                    "UPDATE users SET email_verified_at = created_at "
                    "WHERE email_verified_at IS NULL AND password_hash IS NOT NULL"
                ))

        if "users" in existing_tables:
            if "free_checkins_used" in _columns_now(conn, "users"):
                conn.execute(text(
                    "UPDATE users SET free_checkins_used = 0 WHERE free_checkins_used IS NULL"
                ))

        if "clients" in existing_tables:
            if "checkin_token" in _columns_now(conn, "clients"):
                rows_needing_token = conn.execute(
                    text("SELECT id FROM clients WHERE checkin_token IS NULL")
                ).fetchall()
                for (client_id,) in rows_needing_token:
                    conn.execute(
                        text("UPDATE clients SET checkin_token = :token WHERE id = :id"),
                        {"token": secrets.token_urlsafe(24), "id": client_id},
                    )
