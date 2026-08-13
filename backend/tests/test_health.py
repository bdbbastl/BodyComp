def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_lifespan_does_not_touch_real_database(client, db_session):
    """Beweist, dass der FastAPI-lifespan-Hook (Base.metadata.create_all,
    run_lightweight_migrations) tatsächlich gegen die isolierte Test-DB
    läuft, nicht gegen die echte backend/data/bodycomp.db - siehe Code-
    Review-Fund: ein monkeypatch auf app.core.database reicht NICHT, weil
    app/main.py die Namen per `from ... import engine, SessionLocal`
    bare-name-importiert.

    Poses werden inzwischen nicht mehr global beim App-Start geseedet,
    sondern erst pro Client bei dessen Anlage (siehe app/core/seed.py:
    seed_default_poses_for_client). Diese Assertion prüft stattdessen
    direkt, dass die `poses`-Tabelle in der isolierten Test-DB existiert
    und abfragbar ist (0 Zeilen) - das beweist weiterhin, dass
    Base.metadata.create_all gegen `db_session`s Engine lief, nicht
    gegen die echte DB.
    """
    from app.models.pose import Pose

    poses_in_test_db = db_session.query(Pose).count()
    assert poses_in_test_db == 0
