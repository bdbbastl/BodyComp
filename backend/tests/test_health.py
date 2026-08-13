from fastapi.testclient import TestClient


def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_lifespan_does_not_touch_real_database(client, db_session, monkeypatch):
    """Beweist, dass der FastAPI-lifespan-Hook tatsächlich gegen die
    isolierte Test-DB läuft, nicht gegen die echte
    backend/data/bodycomp.db - siehe Code-Review-Fund: ein monkeypatch
    auf app.core.database reicht NICHT, weil app/main.py die Namen per
    `from ... import engine, SessionLocal` bare-name-importiert.

    WICHTIG: `db_session`s eigene Fixture-Vorbereitung ruft bereits
    selbst `Base.metadata.create_all(bind=engine)` auf der isolierten
    Engine auf, BEVOR `TestClient`/`lifespan()` überhaupt starten (siehe
    tests/conftest.py). Eine bloße Prüfung wie "poses-Tabelle in
    db_session existiert und ist leer" würde also identisch grün sein,
    selbst wenn der `monkeypatch.setattr(main_module, "engine"/
    "SessionLocal", ...)`-Mechanismus in `client` komplett kaputt wäre
    und `lifespan()` in Wahrheit gegen die echte DB liefe. Das würde die
    eigentliche Regression nicht erkennen.

    Deshalb spionieren wir hier `run_lightweight_migrations` aus (wird
    von `lifespan()` mit dem tatsächlich verwendeten `engine`-Objekt
    aufgerufen) und prüfen, dass dieses Objekt `is` die gepatchte,
    isolierte Test-Engine - und ausdrücklich NICHT
    `app.core.database.engine` (die echte Engine für bodycomp.db).
    """
    import app.core.database as database_module
    import app.main as main_module

    captured_engines = []
    original = main_module.run_lightweight_migrations

    def spy(engine):
        captured_engines.append(engine)
        return original(engine)

    monkeypatch.setattr(main_module, "run_lightweight_migrations", spy)

    with TestClient(main_module.app, base_url="https://testserver"):
        pass

    assert len(captured_engines) == 1
    assert captured_engines[0] is main_module.engine
    assert captured_engines[0] is not database_module.engine
