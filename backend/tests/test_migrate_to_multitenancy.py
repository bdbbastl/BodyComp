from datetime import datetime

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.migrate_to_multitenancy import migrate_to_multitenancy
from app.core.migrations import run_lightweight_migrations
from app.models.client import Client
from app.models.user import User


def _make_legacy_engine(tmp_path):
    """Baut eine Engine, die exakt so aussieht wie eine ECHTE Alt-DB von
    vor der Mandantenfähigkeit: poses/day_logs/photos existieren OHNE
    client_id-Spalte (die Tabellen entstehen hier per rohem CREATE TABLE,
    nicht per ORM/`create_all`, damit die NOT-NULL-Constraint auf
    `client_id` in den aktuellen Models - eine bewusste, geprüfte
    Tenant-Isolations-Absicherung aus Task 7, siehe Code-Review zu Commit
    9b5d76c - unangetastet bleibt). `run_lightweight_migrations` trägt die
    Spalte anschließend genauso nach, wie sie es auch gegen eine echte
    Alt-DB täte (ALTER TABLE ... ADD COLUMN client_id INTEGER, nullable,
    ohne Constraint)."""
    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")

    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE poses ("
                "id INTEGER PRIMARY KEY, name VARCHAR(100), sort_order INTEGER, "
                "created_at DATETIME)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE day_logs ("
                "id INTEGER PRIMARY KEY, date DATE, weight_kg FLOAT, "
                "notes VARCHAR(500), created_at DATETIME, updated_at DATETIME)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE photos ("
                "id INTEGER PRIMARY KEY, filename VARCHAR(255), "
                "original_path VARCHAR(1000), normalized_path VARCHAR(1000), "
                "preview_path VARCHAR(1000), thumbnail_path VARCHAR(1000), "
                "taken_at DATETIME, status VARCHAR(30), pose_id INTEGER, "
                "day_log_id INTEGER, landmarks_json TEXT, width INTEGER, "
                "height INTEGER, created_at DATETIME, updated_at DATETIME)"
            )
        )

    # users/clients existieren in einer Alt-DB noch gar nicht - die legt
    # migrate_to_multitenancy() über create_account() (ORM) frisch an.
    Base.metadata.create_all(bind=engine, tables=[User.__table__, Client.__table__])

    return engine


def _seed_pre_migration_data(engine):
    """Legt Pose/DayLog/Photo per rohem SQL an (die ORM-Models erlauben
    seit Task 7 bewusst kein NULL für client_id mehr) - simuliert den
    Stand vor der Mandantenfähigkeit, wo die Spalte noch gar nicht
    existierte."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO poses (id, name, sort_order, created_at) "
                "VALUES (1, 'Front Double Biceps', 0, :created_at)"
            ),
            {"created_at": datetime(2026, 1, 1)},
        )
        conn.execute(
            text(
                "INSERT INTO day_logs (id, date, weight_kg, created_at, updated_at) "
                "VALUES (1, '2026-01-01', 80.0, :now, :now)"
            ),
            {"now": datetime(2026, 1, 1)},
        )
        conn.execute(
            text(
                "INSERT INTO photos (id, filename, original_path, taken_at, status, "
                "pose_id, day_log_id, created_at, updated_at) "
                "VALUES (1, 'test.jpg', 'photos_processed/2026-01-01/test.jpg', "
                ":taken_at, 'PROCESSED', 1, 1, :taken_at, :taken_at)"
            ),
            {"taken_at": datetime(2026, 1, 1, 12, 0, 0)},
        )


def test_migration_creates_account_and_client(tmp_path):
    engine = _make_legacy_engine(tmp_path)
    _seed_pre_migration_data(engine)
    run_lightweight_migrations(engine)

    session = sessionmaker(bind=engine)()
    try:
        migrate_to_multitenancy(
            session,
            email="basti@example.com",
            password="Grindcore123!",
            display_name="Basti",
        )

        user = session.query(User).filter(User.email == "basti@example.com").first()
        assert user is not None
        assert user.account_type.value == "coach"

        client_row = session.query(Client).filter(Client.owner_id == user.id).first()
        assert client_row is not None
        assert client_row.name == "Mein Profil"
    finally:
        session.close()


def test_migration_backfills_client_id_on_existing_rows(tmp_path):
    engine = _make_legacy_engine(tmp_path)
    _seed_pre_migration_data(engine)
    run_lightweight_migrations(engine)

    session = sessionmaker(bind=engine)()
    try:
        migrate_to_multitenancy(
            session,
            email="basti@example.com",
            password="Grindcore123!",
            display_name="Basti",
        )

        client_row = session.query(Client).first()

        with engine.connect() as conn:
            pose_client_id = conn.execute(text("SELECT client_id FROM poses WHERE id = 1")).scalar()
            daylog_client_id = conn.execute(
                text("SELECT client_id FROM day_logs WHERE id = 1")
            ).scalar()
            photo_client_id = conn.execute(text("SELECT client_id FROM photos WHERE id = 1")).scalar()

        assert pose_client_id == client_row.id
        assert daylog_client_id == client_row.id
        assert photo_client_id == client_row.id
    finally:
        session.close()


def test_migration_is_a_noop_when_a_user_already_exists(tmp_path):
    engine = _make_legacy_engine(tmp_path)
    _seed_pre_migration_data(engine)
    run_lightweight_migrations(engine)

    session = sessionmaker(bind=engine)()
    try:
        migrate_to_multitenancy(
            session, email="basti@example.com", password="Grindcore123!", display_name="Basti"
        )
        user_count_after_first_run = session.query(User).count()

        migrate_to_multitenancy(
            session, email="basti@example.com", password="Grindcore123!", display_name="Basti"
        )
        user_count_after_second_run = session.query(User).count()

        assert user_count_after_first_run == user_count_after_second_run == 1
    finally:
        session.close()
