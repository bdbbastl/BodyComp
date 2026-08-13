"""
Sehr leichtgewichtige Schema-Migration für den POC.

`Base.metadata.create_all()` legt fehlende TABELLEN an, ändert aber nie
Spalten einer bereits existierenden Tabelle. Für neue nullable Spalten an
bestehenden Tabellen (z.B. `preview_path`) reicht hier ein simples
"ALTER TABLE ... ADD COLUMN", statt gleich Alembic aufzusetzen. Für die
spätere Cloud-Version sollte das durch echte Alembic-Migrationen ersetzt
werden (siehe README).
"""
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

# (Tabelle, Spalte, SQL-Typ) - hier eintragen, wenn ein neues nullable
# Feld zu einem bestehenden Model hinzukommt.
_PENDING_COLUMNS: list[tuple[str, str, str]] = [
    ("photos", "preview_path", "VARCHAR(1000)"),
    ("photos", "thumbnail_path", "VARCHAR(1000)"),
]


def run_lightweight_migrations(engine: Engine) -> None:
    inspector = inspect(engine)
    if "photos" not in inspector.get_table_names():
        return  # Frisch angelegte DB - create_all() hat die Spalte schon.

    existing_columns = {col["name"] for col in inspector.get_columns("photos")}

    with engine.begin() as conn:
        for table, column, sql_type in _PENDING_COLUMNS:
            if column in existing_columns:
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))
