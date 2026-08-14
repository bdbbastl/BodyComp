"""Reproduziert einen echten Bug: die reale `users`-Tabelle hatte
`password_hash` als inline NOT-NULL-Constraint (aus Stufe 1, bevor
Google-only-Accounts existierten) und `google_id` ganz ohne Unique-Index
(nur per ALTER TABLE ADD COLUMN nachgetragen). Beide Probleme blockierten
echte Google-Logins gegen die Produktions-DB mit einem
IntegrityError."""
from sqlalchemy import create_engine, inspect, text

from app.core.migrate_users_nullable_password import fix_users_password_hash_nullable


def _make_legacy_users_engine(tmp_path):
    """Baut exakt die reale Alt-Schema-Form nach: password_hash NOT NULL
    inline, google_id als reine ALTER-TABLE-Spalte ohne Index."""
    db_path = tmp_path / "legacy_users.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE users ("
            "id INTEGER NOT NULL, "
            "email VARCHAR(255) NOT NULL, "
            "password_hash VARCHAR(255) NOT NULL, "
            "display_name VARCHAR(100) NOT NULL, "
            "account_type VARCHAR(6) NOT NULL, "
            "created_at DATETIME NOT NULL, google_id VARCHAR(255), "
            "email_verified_at DATETIME, privacy_accepted_at DATETIME, "
            "sessions_invalidated_at DATETIME, "
            "PRIMARY KEY (id))"
        ))
        conn.execute(text("CREATE UNIQUE INDEX ix_users_email ON users (email)"))
        conn.execute(text(
            "INSERT INTO users (id, email, password_hash, display_name, account_type, created_at) "
            "VALUES (1, 'basti@example.com', 'somehash', 'Basti', 'SINGLE', '2026-01-01 00:00:00')"
        ))
    return engine


def test_fix_makes_password_hash_nullable(tmp_path):
    engine = _make_legacy_users_engine(tmp_path)
    fix_users_password_hash_nullable(engine)

    inspector = inspect(engine)
    columns = {c["name"]: c for c in inspector.get_columns("users")}
    assert columns["password_hash"]["nullable"] is True


def test_fix_allows_google_only_user_insert(tmp_path):
    engine = _make_legacy_users_engine(tmp_path)
    fix_users_password_hash_nullable(engine)

    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO users (id, email, password_hash, display_name, account_type, created_at, google_id) "
            "VALUES (2, 'google@example.com', NULL, 'Google User', 'SINGLE', '2026-01-01 00:00:00', 'sub-123')"
        ))
        count = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
    assert count == 2


def test_fix_preserves_existing_data(tmp_path):
    engine = _make_legacy_users_engine(tmp_path)
    fix_users_password_hash_nullable(engine)

    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT email, password_hash, display_name FROM users WHERE id = 1"
        )).fetchone()
    assert row.email == "basti@example.com"
    assert row.password_hash == "somehash"
    assert row.display_name == "Basti"


def test_fix_adds_unique_index_on_google_id(tmp_path):
    engine = _make_legacy_users_engine(tmp_path)
    fix_users_password_hash_nullable(engine)

    inspector = inspect(engine)
    unique_indexes = [
        idx for idx in inspector.get_indexes("users")
        if idx.get("unique") and idx.get("column_names") == ["google_id"]
    ]
    assert len(unique_indexes) == 1


def test_fix_is_idempotent(tmp_path):
    engine = _make_legacy_users_engine(tmp_path)
    fix_users_password_hash_nullable(engine)
    fix_users_password_hash_nullable(engine)  # zweiter Aufruf darf nicht crashen

    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
    assert count == 1


def test_fix_is_safe_on_fresh_create_all_schema(tmp_path):
    """Frische DB via Base.metadata.create_all() hat password_hash schon
    nullable und google_id schon mit Unique-Index - Fix muss No-Op sein."""
    from app.core.database import Base

    db_path = tmp_path / "fresh.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    import app.models.user  # noqa: F401
    import app.models.client  # noqa: F401
    import app.models.email_token  # noqa: F401
    import app.models.app_setting  # noqa: F401

    Base.metadata.create_all(bind=engine)
    fix_users_password_hash_nullable(engine)  # sollte klaglos No-Op sein

    inspector = inspect(engine)
    columns = {c["name"]: c for c in inspector.get_columns("users")}
    assert columns["password_hash"]["nullable"] is True


def test_fix_resumes_cleanly_after_simulated_crash(tmp_path):
    """Simuliert einen Absturz mitten im Table-Rebuild (users_new bleibt
    liegen) - der nächste Aufruf muss das aufräumen statt zu crashen."""
    engine = _make_legacy_users_engine(tmp_path)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE users_new (id INTEGER PRIMARY KEY, email VARCHAR(255))"
        ))

    fix_users_password_hash_nullable(engine)  # darf nicht an "table already exists" scheitern

    inspector = inspect(engine)
    columns = {c["name"]: c for c in inspector.get_columns("users")}
    assert columns["password_hash"]["nullable"] is True
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
    assert count == 1
