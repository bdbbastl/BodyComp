from datetime import datetime, timezone
from unittest.mock import patch

from app.models.email_token import EmailToken, EmailTokenPurpose
from app.models.user import User
from app.services.auth import create_email_token, hash_email_token, hash_password, verify_password


def _make_verified_user(db_session, email="basti@example.com", password="OldPass123!"):
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name="Basti",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_forgot_password_sends_email_for_existing_user(client, db_session):
    _make_verified_user(db_session)
    with patch("app.routers.auth.send_password_reset_email") as mock_send:
        response = client.post("/api/auth/forgot-password", json={"email": "basti@example.com"})
    assert response.status_code == 204
    assert mock_send.call_count == 1


def test_forgot_password_is_silent_for_unknown_email(client, db_session):
    with patch("app.routers.auth.send_password_reset_email") as mock_send:
        response = client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
    assert response.status_code == 204
    assert mock_send.call_count == 0


def test_forgot_password_is_silent_for_google_only_account(client, db_session):
    google_user = User(
        email="google@example.com", display_name="G", google_id="sub-1",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(google_user)
    db_session.commit()

    with patch("app.routers.auth.send_password_reset_email") as mock_send:
        response = client.post("/api/auth/forgot-password", json={"email": "google@example.com"})
    assert response.status_code == 204
    assert mock_send.call_count == 0


def test_reset_password_with_valid_token_changes_password_and_invalidates_sessions(client, db_session):
    user = _make_verified_user(db_session)
    raw_token = create_email_token(user_id=user.id, purpose=EmailTokenPurpose.RESET_PASSWORD.value)
    db_session.add(EmailToken(
        user_id=user.id,
        token_hash=hash_email_token(raw_token),
        purpose=EmailTokenPurpose.RESET_PASSWORD,
        expires_at=datetime.now(timezone.utc).replace(year=2030),
    ))
    db_session.commit()

    response = client.post(
        "/api/auth/reset-password", json={"token": raw_token, "new_password": "NewPass456!"}
    )
    assert response.status_code == 204

    db_session.refresh(user)
    assert verify_password("NewPass456!", user.password_hash)
    assert user.sessions_invalidated_at is not None


def test_reset_password_with_used_token_fails(client, db_session):
    user = _make_verified_user(db_session)
    raw_token = create_email_token(user_id=user.id, purpose=EmailTokenPurpose.RESET_PASSWORD.value)
    db_session.add(EmailToken(
        user_id=user.id,
        token_hash=hash_email_token(raw_token),
        purpose=EmailTokenPurpose.RESET_PASSWORD,
        expires_at=datetime.now(timezone.utc).replace(year=2030),
        used_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    response = client.post(
        "/api/auth/reset-password", json={"token": raw_token, "new_password": "NewPass456!"}
    )
    assert response.status_code == 400


def test_old_session_rejected_after_password_reset(client, db_session):
    user = _make_verified_user(db_session)
    login_resp = client.post("/api/auth/login", json={"email": "basti@example.com", "password": "OldPass123!"})
    assert login_resp.status_code == 200

    raw_token = create_email_token(user_id=user.id, purpose=EmailTokenPurpose.RESET_PASSWORD.value)
    db_session.add(EmailToken(
        user_id=user.id,
        token_hash=hash_email_token(raw_token),
        purpose=EmailTokenPurpose.RESET_PASSWORD,
        expires_at=datetime.now(timezone.utc).replace(year=2030),
    ))
    db_session.commit()
    client.post("/api/auth/reset-password", json={"token": raw_token, "new_password": "NewPass456!"})

    # altes Session-Cookie (vom Login vor dem Reset) darf jetzt nicht mehr gelten
    me_response = client.get("/api/auth/me")
    assert me_response.status_code == 401
