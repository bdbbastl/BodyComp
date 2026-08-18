from datetime import datetime, timezone

from app.models.email_token import EmailToken, EmailTokenPurpose
from app.models.user import User
from app.services.auth import create_email_token, hash_email_token, hash_password


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


def test_me_includes_created_at_and_has_google_account(client, db_session):
    _make_user(db_session)
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    body = response.json()
    assert body["created_at"] is not None
    assert body["has_google_account"] is False


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


def test_me_includes_billing_fields(client, db_session):
    _make_user(db_session)
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})
    response = client.get("/api/auth/me")
    body = response.json()
    assert "subscription_status" in body
    assert "subscription_tier" in body
    assert "free_checkins_used" in body
    assert body["free_checkins_used"] == 0


def test_complete_onboarding_sets_timestamp(client, db_session):
    _make_user(db_session)
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})
    response = client.patch("/api/auth/onboarding-complete")
    assert response.status_code == 200
    assert response.json()["onboarding_completed_at"] is not None


def test_complete_onboarding_requires_login(client, db_session):
    response = client.patch("/api/auth/onboarding-complete")
    assert response.status_code == 401


def test_verify_email_sends_welcome_email_only_once(client, db_session, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.routers.auth.send_welcome_email", lambda **kwargs: sent.append(kwargs)
    )

    user = User(
        email="new@example.com",
        password_hash=hash_password("Grindcore123!"),
        display_name="New",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    raw_token = create_email_token(user_id=user.id, purpose=EmailTokenPurpose.VERIFY_EMAIL.value)
    db_session.add(EmailToken(
        user_id=user.id,
        token_hash=hash_email_token(raw_token),
        purpose=EmailTokenPurpose.VERIFY_EMAIL,
        expires_at=datetime.now(timezone.utc).replace(year=2030),
    ))
    db_session.commit()

    response1 = client.get(f"/api/auth/verify-email?token={raw_token}")
    assert response1.status_code == 200
    assert len(sent) == 1
    assert sent[0]["to"] == "new@example.com"

    raw_token_2 = create_email_token(user_id=user.id, purpose=EmailTokenPurpose.VERIFY_EMAIL.value)
    db_session.add(EmailToken(
        user_id=user.id,
        token_hash=hash_email_token(raw_token_2),
        purpose=EmailTokenPurpose.VERIFY_EMAIL,
        expires_at=datetime.now(timezone.utc).replace(year=2030),
    ))
    db_session.commit()

    response2 = client.get(f"/api/auth/verify-email?token={raw_token_2}")
    assert response2.status_code == 200
    assert len(sent) == 1
