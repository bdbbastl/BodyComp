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
]


def run_lightweight_migrations(engine: Engine) -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, column, sql_type in _PENDING_COLUMNS:
            if table not in existing_tables:
                continue  # Frisch angelegte DB - create_all() hat die Spalte schon.
            existing_columns = {col["name"] for col in inspector.get_columns(table)}
            if column in existing_columns:
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))
