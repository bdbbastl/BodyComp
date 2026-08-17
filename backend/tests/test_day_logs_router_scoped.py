from datetime import datetime, timezone

from app.models.user import User
from app.services.auth import hash_password


def _login_and_get_client(client, db_session, email="a@b.com", password="pw12345"):
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name="A",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.commit()
    client.post("/api/auth/login", json={"email": email, "password": password})
    created = client.post("/api/clients", json={"name": "Kunde"}).json()
    return created["id"]


def test_daylogs_scoped_to_client(client, db_session):
    client_id_a = _login_and_get_client(client, db_session, email="a@b.com", password="pw12345")
    client.put(f"/api/clients/{client_id_a}/day-logs", json={"date": "2026-01-01", "weight_kg": 80})
    client.post("/api/auth/logout")

    client_id_b = _login_and_get_client(client, db_session, email="c@d.com", password="pw67890")
    put_resp = client.put(
        f"/api/clients/{client_id_b}/day-logs", json={"date": "2026-01-01", "weight_kg": 90}
    )
    assert put_resp.status_code == 200  # gleiches Datum, anderer Client - darf nicht kollidieren

    logs_b = client.get(f"/api/clients/{client_id_b}/day-logs").json()
    assert len(logs_b) == 1
    assert logs_b[0]["weight_kg"] == 90


def test_cannot_access_foreign_client_daylogs(client, db_session):
    client_id_a = _login_and_get_client(client, db_session, email="a@b.com", password="pw12345")
    client.post("/api/auth/logout")
    _login_and_get_client(client, db_session, email="c@d.com", password="pw67890")

    response = client.get(f"/api/clients/{client_id_a}/day-logs")
    assert response.status_code == 404


def test_upsert_day_log_blocked_for_single_account_after_free_quota(client, db_session):
    # Default account_type ist bereits SINGLE (siehe User-Modell).
    client_id = _login_and_get_client(client, db_session)

    # Erste 2 kostenlos.
    r1 = client.put(f"/api/clients/{client_id}/day-logs", json={"date": "2026-01-01", "weight_kg": 80})
    r2 = client.put(f"/api/clients/{client_id}/day-logs", json={"date": "2026-01-02", "weight_kg": 79.5})
    assert r1.status_code == 200
    assert r2.status_code == 200

    # 3. neuer Tag -> blockiert.
    r3 = client.put(f"/api/clients/{client_id}/day-logs", json={"date": "2026-01-03", "weight_kg": 79})
    assert r3.status_code == 402


def test_upsert_day_log_updating_existing_day_does_not_consume_quota(client, db_session):
    client_id = _login_and_get_client(client, db_session)

    client.put(f"/api/clients/{client_id}/day-logs", json={"date": "2026-01-01", "weight_kg": 80})
    client.put(f"/api/clients/{client_id}/day-logs", json={"date": "2026-01-02", "weight_kg": 79.5})
    # Denselben Tag NOCHMAL aktualisieren - darf NICHT als 3. Check-in zählen.
    response = client.put(
        f"/api/clients/{client_id}/day-logs", json={"date": "2026-01-01", "weight_kg": 80.5}
    )
    assert response.status_code == 200


def test_upsert_day_log_accepts_comma_decimal_weight(client, db_session):
    client_id = _login_and_get_client(client, db_session)

    response = client.put(
        f"/api/clients/{client_id}/day-logs", json={"date": "2026-01-01", "weight_kg": "76,05"}
    )
    assert response.status_code == 200
    assert response.json()["weight_kg"] == 76.05
