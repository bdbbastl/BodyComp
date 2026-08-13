def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_lifespan_does_not_touch_real_database(client, db_session):
    """Beweist, dass der FastAPI-lifespan-Hook (Base.metadata.create_all,
    seed_default_poses) tatsächlich gegen die isolierte Test-DB läuft,
    nicht gegen die echte backend/data/bodycomp.db - siehe Code-Review-
    Fund: ein monkeypatch auf app.core.database reicht NICHT, weil
    app/main.py die Namen per `from ... import engine, SessionLocal`
    bare-name-importiert.

    Falls der lifespan-Hook (fälschlich) gegen die echte DB liefe, wäre
    deren `poses`-Tabelle bereits befüllt (siehe Bug-Beschreibung), sodass
    `seed_default_poses` dort ein No-Op wäre - die Test-DB (`db_session`)
    bliebe dann leer und dieser Assert schlägt fehl. Nur wenn der Hook
    wirklich gegen `db_session`s Engine lief, sind hier 7 Posen vorhanden.
    """
    from app.models.pose import Pose

    poses_in_test_db = db_session.query(Pose).count()
    assert poses_in_test_db == 7  # DEFAULT_POSES aus app/core/seed.py
