from datetime import datetime, timezone

from app.models.user import User
from app.services.auth import hash_password


def _make_user(db_session, email="basti@example.com", password="Grindcore123!"):
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name="Basti",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_login_with_correct_credentials_sets_cookie(client, db_session):
    _make_user(db_session)
    response = client.post(
        "/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"}
    )
    assert response.status_code == 200
    assert "session" in response.cookies


def test_login_with_wrong_password_fails(client, db_session):
    _make_user(db_session)
    response = client.post(
        "/api/auth/login", json={"email": "basti@example.com", "password": "wrong"}
    )
    assert response.status_code == 401
    assert "session" not in response.cookies


def test_login_with_unknown_email_fails(client, db_session):
    response = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": "x"}
    )
    assert response.status_code == 401


def test_me_requires_session(client, db_session):
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_me_returns_current_user_after_login(client, db_session):
    _make_user(db_session)
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "basti@example.com"
    assert body["display_name"] == "Basti"
    assert body["account_type"] == "single"


def test_logout_clears_session(client, db_session):
    _make_user(db_session)
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})
    client.post("/api/auth/logout")
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_switch_to_coach_flips_account_type(client, db_session):
    _make_user(db_session)
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})

    response = client.post("/api/auth/switch-to-coach")
    assert response.status_code == 200
    assert response.json()["account_type"] == "coach"

    me_response = client.get("/api/auth/me")
    assert me_response.json()["account_type"] == "coach"


def test_switch_to_coach_is_idempotent(client, db_session):
    _make_user(db_session)
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})
    client.post("/api/auth/switch-to-coach")
    second_response = client.post("/api/auth/switch-to-coach")
    assert second_response.status_code == 200
    assert second_response.json()["account_type"] == "coach"
