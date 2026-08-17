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


def test_checkin_token_backfilled_on_pre_existing_clients_table(tmp_path):
    """Regression: die Migration muss neu hinzugefügte Spalten SOFORT
    zurücklesen können, um sie im selben Lauf zu befüllen (Backfill) -
    nicht erst beim nächsten Prozessstart. Ein `inspect(engine)`-Inspector
    nutzt intern eine eigene Connection und sieht die per ALTER TABLE
    gerade erst hinzugefügte, noch nicht committete Spalte NICHT - das
    hat den checkin_token-Backfill live gegen eine echte Bestands-DB
    beim ersten Migrationslauf stillschweigend übersprungen (gefunden
    beim Deploy von feature/checkin-review-platform)."""
    db_path = tmp_path / "old.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE clients (id INTEGER PRIMARY KEY, owner_id INTEGER, "
            "name VARCHAR(100), created_at DATETIME)"
        ))
        conn.execute(text(
            "INSERT INTO clients (id, owner_id, name, created_at) "
            "VALUES (1, 1, 'Max', '2026-01-01')"
        ))

    run_lightweight_migrations(engine)

    with engine.begin() as conn:
        token = conn.execute(
            text("SELECT checkin_token FROM clients WHERE id = 1")
        ).scalar()
    assert token is not None
    assert len(token) >= 20


def test_billing_fields_backfilled_on_pre_existing_users_table(tmp_path):
    """Analog zum checkin_token-Backfill (siehe Test oben) - neue
    Spalten müssen für Bestandsnutzer sinnvolle Defaults bekommen, nicht
    NULL bleiben, wo das Anwendungscode als 'nie initialisiert' vs.
    '0 verbraucht' verwechseln könnte."""
    db_path = tmp_path / "old.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255), "
            "display_name VARCHAR(100), account_type VARCHAR(20), created_at DATETIME)"
        ))
        conn.execute(text(
            "INSERT INTO users (id, email, display_name, account_type, created_at) "
            "VALUES (1, 'a@b.com', 'A', 'SINGLE', '2026-01-01')"
        ))

    run_lightweight_migrations(engine)

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT free_checkins_used FROM users WHERE id = 1")
        ).first()
    assert row[0] == 0


def test_onboarding_completed_at_column_added_to_pre_existing_users_table(tmp_path):
    """Simuliert eine alte DB von vor dem Onboarding-Flow: legt users OHNE
    onboarding_completed_at an, prüft dass die Migration die Spalte
    nachträgt."""
    db_path = tmp_path / "old.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255), "
            "display_name VARCHAR(100), account_type VARCHAR(20), created_at DATETIME)"
        ))
        conn.execute(text(
            "INSERT INTO users (id, email, display_name, account_type, created_at) "
            "VALUES (1, 'a@b.com', 'A', 'SINGLE', '2026-01-01')"
        ))

    run_lightweight_migrations(engine)

    inspector = inspect(engine)
    users_columns = {c["name"] for c in inspector.get_columns("users")}
    assert "onboarding_completed_at" in users_columns
