# backend/tests/test_migrations.py
from sqlalchemy import create_engine, inspect, text

from app.core.migrations import run_lightweight_migrations


def test_client_id_column_added_to_pre_existing_tables(tmp_path):
    """Simuliert eine alte DB von vor der Mandantenfähigkeit: legt poses/
    day_logs/photos OHNE client_id an, prüft dass die Migration die Spalte
    nachträgt."""
    db_path = tmp_path / "old.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE poses (id INTEGER PRIMARY KEY, name VARCHAR(100))"))
        conn.execute(text("CREATE TABLE day_logs (id INTEGER PRIMARY KEY, date DATE)"))
        conn.execute(
            text(
                "CREATE TABLE photos (id INTEGER PRIMARY KEY, original_path VARCHAR(1000), "
                "preview_path VARCHAR(1000), thumbnail_path VARCHAR(1000))"
            )
        )

    run_lightweight_migrations(engine)

    inspector = inspect(engine)
    pose_columns = {c["name"] for c in inspector.get_columns("poses")}
    daylog_columns = {c["name"] for c in inspector.get_columns("day_logs")}
    photo_columns = {c["name"] for c in inspector.get_columns("photos")}
    assert "client_id" in pose_columns
    assert "client_id" in daylog_columns
    assert "client_id" in photo_columns
