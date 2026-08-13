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
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app


@pytest.fixture()
def db_session(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.db"
        engine = create_engine(
            f"sqlite:///{db_path.as_posix()}", connect_args={"check_same_thread": False}
        )
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
