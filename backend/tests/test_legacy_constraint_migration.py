"""Reproduziert einen echten Bug: die reale Legacy-DB hatte `poses.name`
als inline UNIQUE-Constraint (SQLite-Autoindex, nicht per DROP INDEX
entfernbar) und `day_logs.date` als separaten benannten UNIQUE INDEX.
Beide müssen entfernt werden, damit zwei Clients dieselben Pose-Namen/
Datumswerte haben können - siehe migrate_to_multitenancy.py."""
from sqlalchemy import create_engine, inspect, text

from app.core.migrations import run_lightweight_migrations
from app.core.migrate_legacy_unique_constraints import fix_legacy_unique_constraints


def _make_real_legacy_engine(tmp_path):
    """Baut exakt die reale Alt-Schema-Form nach: poses.name mit
    inline UNIQUE (erzeugt SQLite-Autoindex), day_logs.date mit
    separatem benanntem UNIQUE INDEX."""
    db_path = tmp_path / "real_legacy.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE poses ("
            "id INTEGER NOT NULL PRIMARY KEY, "
            "name VARCHAR(100) NOT NULL, "
            "sort_order INTEGER NOT NULL, "
            "created_at DATETIME NOT NULL, "
            "UNIQUE (name))"
        ))
        conn.execute(text(
            "CREATE TABLE day_logs ("
            "id INTEGER NOT NULL PRIMARY KEY, "
            "date DATE NOT NULL, "
            "weight_kg FLOAT, "
            "notes VARCHAR(500), "
            "created_at DATETIME NOT NULL, "
            "updated_at DATETIME NOT NULL)"
        ))
        conn.execute(text("CREATE UNIQUE INDEX ix_day_logs_date ON day_logs (date)"))
        conn.execute(text(
            "INSERT INTO poses (name, sort_order, created_at) VALUES "
            "('Front Double Biceps', 0, '2026-01-01 00:00:00')"
        ))
        conn.execute(text(
            "INSERT INTO day_logs (date, created_at, updated_at) VALUES "
            "('2026-01-01', '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
        ))
    return engine


def test_two_poses_with_same_name_different_client_id_after_migration(tmp_path):
    """Reproduziert den Bug 1:1: nach der vollen Migration (lightweight +
    Constraint-Fix) muss das Anlegen einer zweiten Pose mit demselben
    Namen (aber anderer client_id) funktionieren - vorher schlug das mit
    IntegrityError: UNIQUE constraint failed: poses.name fehl."""
    engine = _make_real_legacy_engine(tmp_path)
    run_lightweight_migrations(engine)  # fügt client_id-Spalten hinzu
    fix_legacy_unique_constraints(engine)

    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE poses SET client_id = 1 WHERE client_id IS NULL"
        ))
        # Das ist der eigentliche Bug-Reproduktionsschritt: zweite Pose,
        # gleicher Name, ANDERE client_id - darf NICHT scheitern.
        conn.execute(text(
            "INSERT INTO poses (name, sort_order, created_at, client_id) VALUES "
            "('Front Double Biceps', 0, '2026-01-01 00:00:00', 2)"
        ))

    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM poses")).scalar()
    assert count == 2


def test_two_day_logs_with_same_date_different_client_id_after_migration(tmp_path):
    engine = _make_real_legacy_engine(tmp_path)
    run_lightweight_migrations(engine)
    fix_legacy_unique_constraints(engine)

    with engine.begin() as conn:
        conn.execute(text("UPDATE day_logs SET client_id = 1 WHERE client_id IS NULL"))
        conn.execute(text(
            "INSERT INTO day_logs (date, created_at, updated_at, client_id) VALUES "
            "('2026-01-01', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 2)"
        ))

    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM day_logs")).scalar()
    assert count == 2


def test_poses_client_id_and_data_preserved_after_constraint_fix(tmp_path):
    """Stellt sicher, dass der Table-Rebuild für poses keine Daten
    verliert oder verfälscht (id, name, sort_order, created_at,
    client_id müssen exakt erhalten bleiben)."""
    engine = _make_real_legacy_engine(tmp_path)
    run_lightweight_migrations(engine)
    with engine.begin() as conn:
        conn.execute(text("UPDATE poses SET client_id = 1"))
    fix_legacy_unique_constraints(engine)

    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT id, name, sort_order, client_id FROM poses"
        )).fetchone()
    assert row.name == "Front Double Biceps"
    assert row.sort_order == 0
    assert row.client_id == 1


def test_fix_is_idempotent_on_fresh_create_all_schema(tmp_path):
    """Eine frische DB via create_all() hat bereits die korrekten
    Composite-Constraints - der Fix darf hier nichts kaputt machen und
    muss ein sicheres No-Op sein."""
    from app.core.database import Base
    import app.models  # noqa: F401  (registriert alle Models an Base.metadata)

    db_path = tmp_path / "fresh.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    Base.metadata.create_all(bind=engine)

    # Läuft zweimal hintereinander, um Idempotenz zu prüfen.
    fix_legacy_unique_constraints(engine)
    fix_legacy_unique_constraints(engine)

    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO poses (name, sort_order, created_at, client_id) VALUES "
            "('X', 0, '2026-01-01 00:00:00', 1)"
        ))
        conn.execute(text(
            "INSERT INTO poses (name, sort_order, created_at, client_id) VALUES "
            "('X', 0, '2026-01-01 00:00:00', 2)"
        ))

    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM poses")).scalar()
    assert count == 2


def test_fix_is_safe_when_tables_do_not_exist(tmp_path):
    db_path = tmp_path / "empty.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    fix_legacy_unique_constraints(engine)  # darf nicht crashen
