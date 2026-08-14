from datetime import datetime

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.migrate_to_multitenancy import migrate_to_multitenancy
from app.core.migrations import run_lightweight_migrations
from app.models.app_setting import AppSetting
from app.models.client import Client
from app.models.user import User

LEGACY_DISPLAY_SETTINGS_VALUE = '{"timeline_columns_max": 7, "timeline_weeks_per_page": 8}'


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


def _seed_legacy_app_settings(engine, value=LEGACY_DISPLAY_SETTINGS_VALUE):
    """Legt `app_settings` exakt so an, wie es in der ECHTEN Alt-DB von
    vor Task 10 aussieht: Einzel-Spalten-PK auf `key`, keine
    `owner_id`-Spalte, mit einer echten bestehenden
    `display_settings`-Zeile."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE app_settings ("
                "\"key\" VARCHAR(100) NOT NULL, "
                "value VARCHAR(2000), "
                "PRIMARY KEY (\"key\"))"
            )
        )
        conn.execute(
            text("INSERT INTO app_settings (\"key\", value) VALUES ('display_settings', :value)"),
            {"value": value},
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


def test_migration_fixes_legacy_app_settings_schema_and_preserves_data(tmp_path):
    """Reproduziert den echten 500er auf GET /api/settings/display:
    eine reale Alt-DB hat `app_settings` noch mit Einzel-PK auf `key`
    und einer echten `display_settings`-Zeile. Nach der Migration muss
    die Zeile erhalten bleiben, per ORM-Composite-PK auffindbar sein
    und dem neu migrierten Account gehören."""
    engine = _make_legacy_engine(tmp_path)
    _seed_pre_migration_data(engine)
    _seed_legacy_app_settings(engine)
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

        inspector = inspect(engine)
        pk_columns = set(inspector.get_pk_constraint("app_settings")["constrained_columns"])
        assert pk_columns == {"owner_id", "key"}

        row = session.get(AppSetting, (user.id, "display_settings"))
        assert row is not None
        assert row.value == LEGACY_DISPLAY_SETTINGS_VALUE
        assert row.owner_id == user.id
    finally:
        session.close()


def test_migration_fixes_app_settings_even_when_user_already_exists(tmp_path):
    """Deckt den exakten realen Zustand dieser Worktree-DB ab: User
    existiert bereits (frühere migrate_to_multitenancy()-Läufe), aber
    `app_settings` bekam den Schema-Fix erst durch einen späteren
    Deploy dieses Fixes. Der frühe No-Op-Return bei existierendem User
    darf den app_settings-Fix nicht verhindern."""
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

        # Simuliert: app_settings existiert erst jetzt in der alten Form
        # (z.B. weil dieser Fix erst in einem späteren Deploy dazukam).
        _seed_legacy_app_settings(engine)

        migrate_to_multitenancy(
            session,
            email="basti@example.com",
            password="Grindcore123!",
            display_name="Basti",
        )

        user = session.query(User).filter(User.email == "basti@example.com").first()
        row = session.get(AppSetting, (user.id, "display_settings"))
        assert row is not None
        assert row.value == LEGACY_DISPLAY_SETTINGS_VALUE
        assert row.owner_id == user.id
    finally:
        session.close()


def test_migration_app_settings_fix_is_idempotent(tmp_path):
    """Zweiter Lauf gegen eine bereits reparierte app_settings-Tabelle
    darf weder crashen noch Daten duplizieren/verlieren."""
    engine = _make_legacy_engine(tmp_path)
    _seed_pre_migration_data(engine)
    _seed_legacy_app_settings(engine)
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

        migrate_to_multitenancy(
            session,
            email="basti@example.com",
            password="Grindcore123!",
            display_name="Basti",
        )

        rows = session.query(AppSetting).all()
        assert len(rows) == 1
        assert rows[0].owner_id == user.id
        assert rows[0].value == LEGACY_DISPLAY_SETTINGS_VALUE
    finally:
        session.close()
