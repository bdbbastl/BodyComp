from unittest.mock import AsyncMock, patch

from app.models.user import AccountType, User
from app.services.auth import hash_password


def test_google_login_redirects_to_google_without_crashing(client):
    # Bewusst NICHT gemockt: prüft, dass SessionMiddleware installiert ist,
    # denn authlibs authorize_redirect greift intern auf request.session zu
    # (State/Nonce fürs CSRF-Schutz), was ohne SessionMiddleware mit einem
    # AssertionError crasht.
    response = client.get("/api/auth/google/login", follow_redirects=False)

    assert response.status_code in (302, 307)
    assert "accounts.google.com" in response.headers["location"]
    assert "session" in response.cookies


def _fake_google_userinfo(sub="google-sub-123", email="google@example.com", name="Google User"):
    return {"sub": sub, "email": email, "email_verified": True, "name": name}


def test_google_callback_creates_new_user(client, db_session):
    with patch("app.routers.auth.oauth.google.authorize_access_token", new_callable=AsyncMock) as mock_token:
        mock_token.return_value = {"userinfo": _fake_google_userinfo()}
        response = client.get("/api/auth/google/callback", follow_redirects=False)

    assert response.status_code in (302, 307)
    user = db_session.query(User).filter(User.google_id == "google-sub-123").first()
    assert user is not None
    assert user.email == "google@example.com"
    assert user.display_name == "Google User"
    assert user.password_hash is None
    assert user.email_verified_at is not None
    assert user.privacy_accepted_at is not None
    assert "session" in response.cookies


def test_google_callback_logs_in_existing_google_user(client, db_session):
    existing = User(
        email="google@example.com",
        display_name="Google User",
        google_id="google-sub-123",
        email_verified_at=None,
    )
    from datetime import datetime, timezone
    existing.email_verified_at = datetime.now(timezone.utc)
    db_session.add(existing)
    db_session.commit()

    with patch("app.routers.auth.oauth.google.authorize_access_token", new_callable=AsyncMock) as mock_token:
        mock_token.return_value = {"userinfo": _fake_google_userinfo()}
        response = client.get("/api/auth/google/callback", follow_redirects=False)

    assert "session" in response.cookies
    assert db_session.query(User).count() == 1  # kein Duplikat


def test_google_callback_links_to_existing_email_password_account(client, db_session):
    from datetime import datetime, timezone
    existing = User(
        email="google@example.com",
        display_name="Existing",
        password_hash=hash_password("Whatever123!"),
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(existing)
    db_session.commit()
    existing_id = existing.id

    with patch("app.routers.auth.oauth.google.authorize_access_token", new_callable=AsyncMock) as mock_token:
        mock_token.return_value = {"userinfo": _fake_google_userinfo()}
        response = client.get("/api/auth/google/callback", follow_redirects=False)

    assert "session" in response.cookies
    db_session.refresh(existing)
    assert existing.google_id == "google-sub-123"
    assert db_session.query(User).count() == 1
    assert existing.id == existing_id
