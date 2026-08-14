from datetime import datetime, timezone

from app.models.user import User
from app.services.auth import hash_password


def _login(client, db_session, email="a@b.com", password="pw12345"):
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name="A",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.commit()
    client.post("/api/auth/login", json={"email": email, "password": password})
    return user


def test_gemini_key_is_scoped_per_account(client, db_session):
    _login(client, db_session, email="a@b.com", password="pw12345")
    client.put("/api/settings/gemini-key", json={"api_key": "AIzaSyAAAA1111"})
    status_a = client.get("/api/settings/gemini-key").json()
    assert status_a["configured"] is True
    assert status_a["last4"] == "1111"
    client.post("/api/auth/logout")

    _login(client, db_session, email="c@d.com", password="pw67890")
    status_c = client.get("/api/settings/gemini-key").json()
    assert status_c["configured"] is False


def test_gemini_key_requires_login(client, db_session):
    response = client.get("/api/settings/gemini-key")
    assert response.status_code == 401


def test_display_settings_scoped_per_account(client, db_session):
    _login(client, db_session, email="a@b.com", password="pw12345")
    client.put("/api/settings/display", json={"timeline_columns_max": 3, "timeline_weeks_per_page": 4})
    result = client.get("/api/settings/display").json()
    assert result["timeline_columns_max"] == 3
