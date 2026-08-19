"""
Pytest-Fixtures: jede Testfunktion bekommt eine frische, leere SQLite-DB in
einer temporären Datei (nicht in-memory, weil die App mit
`connect_args={"check_same_thread": False}` arbeitet und manche Endpunkte
mehrere Connections aus demselben Engine ziehen - eine echte Datei verhält
sich da vorhersehbarer als eine In-Memory-DB, die pro Connection neu wäre).

Wichtig: `TestClient(app)` als Context-Manager löst FastAPIs `lifespan`-Handler
aus (siehe `app/main.py`), der `Base.metadata.create_all` und
`seed_default_poses` direkt gegen `engine`/`SessionLocal` ausführt - nicht
gegen die per `get_db`-Dependency überschriebene Session. `app/main.py`
importiert `engine`/`SessionLocal` per `from app.core.database import ...`
(bare-name-Import), wodurch `app.main` eigene, unabhängige Namensbindungen
im eigenen Modul-Namespace erhält. Ein `monkeypatch.setattr(app.core.database,
"engine", ...)` patcht nur das Attribut auf `app.core.database` und erreicht
`app.main`s bereits gebundenen Namen NICHT. Deshalb patchen wir hier
`app.main`s eigene Namen direkt - das ist die Stelle, die `lifespan()`
tatsächlich liest -, bevor der `client`-Fixture den TestClient (und damit
den Lifespan-Hook) startet.
"""
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.routers import auth as auth_router


@pytest.fixture(autouse=True)
def _isolate_file_storage(monkeypatch, tmp_path):
    """Zwingt JEDEN Test auf lokalen Storage in einem Temp-Verzeichnis,
    unabhängig davon, was echte Umgebungsvariablen (z.B. BODYCOMP_
    STORAGE_BACKEND=r2, BODYCOMP_R2_*) gerade konfigurieren.

    Kritischer Live-Vorfall (gefunden 2026-08-19): der Dockerfile-
    Deploy-Gate führt `pytest -q` im Railway-Build-Container aus, wo die
    echten R2-Zugangsdaten als Env-Vars gesetzt sind. Ohne diese Isolation
    hat test_public_checkin_router.py's Path-Traversal-Test
    (test_submit_checkin_sanitizes_path_traversal_filename) bei JEDEM
    Deploy eine echte "evil.jpg"-Fake-Datei nach R2 hochgeladen - landete
    dort unter photos_incoming/1/, kollidierte mit dem echten Client 1
    (erster je angelegter Kunde) und tauchte im Import-Screen als
    Geister-Foto auf. storage_backend war nie auf "local" erzwungen."""
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "data_dir", tmp_path)


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    # Die RateLimiter-Instanzen in app/routers/auth.py sind Modul-Level-
    # Singletons (In-Memory-Zähler pro Prozess, siehe core/rate_limit.py) -
    # ohne Reset zwischen Tests summieren sich Hits über die gesamte
    # Testsession hinweg auf und lösen irgendwann fälschlich 429 statt der
    # jeweils erwarteten Statuscodes aus.
    auth_router.signup_rate_limit._hits.clear()
    auth_router.login_rate_limit._hits.clear()
    auth_router.resend_verification_rate_limit._hits.clear()
    auth_router.change_email_rate_limit._hits.clear()
    from app.routers import public_checkin as public_checkin_router
    public_checkin_router.checkin_submit_rate_limit._hits.clear()
    yield


@pytest.fixture()
def db_session(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.db"
        engine = create_engine(
            f"sqlite:///{db_path.as_posix()}", connect_args={"check_same_thread": False}
        )

        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(bind=engine)
        TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        import app.main as main_module

        monkeypatch.setattr(main_module, "engine", engine)
        monkeypatch.setattr(main_module, "SessionLocal", TestSessionLocal)

        session = TestSessionLocal()
        try:
            yield session
        finally:
            session.close()
            engine.dispose()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    # base_url mit https, weil das Session-Cookie `secure=True` setzt (siehe
    # app/routers/auth.py) - httpx' Cookie-Jar würde ein Secure-Cookie sonst
    # bei einem http://-Base-URL stillschweigend nicht zurücksenden.
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()
