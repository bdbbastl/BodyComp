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


def _login_as(client, user):
    """Setzt das Session-Cookie direkt für den gegebenen User, ohne den
    /api/auth/login-Endpunkt zu nutzen. Nötig für Fälle wie Google-only-
    Accounts, die sich nicht per Passwort einloggen können."""
    from app.services.auth import SESSION_COOKIE_NAME, create_session_token

    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)
    return token


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


def test_change_password_requires_login(client, db_session):
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": "x", "new_password": "NewPass123!"},
    )
    assert response.status_code == 401


def test_change_password_rejects_wrong_current_password(client, db_session):
    _make_user(db_session)
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": "wrong", "new_password": "NewPass123!"},
    )
    assert response.status_code == 401


def test_change_password_rejects_too_short_new_password(client, db_session):
    _make_user(db_session)
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": "Grindcore123!", "new_password": "short"},
    )
    assert response.status_code == 422


def test_change_password_succeeds_and_new_password_works_on_next_login(client, db_session):
    _make_user(db_session)
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": "Grindcore123!", "new_password": "NewPass123!"},
    )
    assert response.status_code == 204

    client.post("/api/auth/logout")
    login_response = client.post(
        "/api/auth/login", json={"email": "basti@example.com", "password": "NewPass123!"}
    )
    assert login_response.status_code == 200


def test_change_password_rejects_google_only_account(client, db_session):
    user = User(
        email="google@example.com",
        password_hash=None,
        google_id="google-sub-123",
        display_name="Google User",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.commit()
    _login_as(client, user)

    response = client.post(
        "/api/auth/change-password",
        json={"current_password": "anything", "new_password": "NewPass123!"},
    )
    assert response.status_code == 400


def test_change_password_invalidates_other_sessions_but_keeps_caller_logged_in(client, db_session):
    _make_user(db_session)
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})
    old_session_cookie = client.cookies.get("session")

    response = client.post(
        "/api/auth/change-password",
        json={"current_password": "Grindcore123!", "new_password": "NewPass123!"},
    )
    assert response.status_code == 204

    # Die alte Session (z.B. ein gekapertes Gerät) muss jetzt tot sein.
    client.cookies.set("session", old_session_cookie)
    old_session_response = client.get("/api/auth/me")
    assert old_session_response.status_code == 401

    # Das neue, vom change-password-Response gesetzte Cookie soll aber
    # weiterhin funktionieren - der aufrufende Browser bleibt eingeloggt.
    new_session_cookie = response.cookies.get("session")
    client.cookies.set("session", new_session_cookie)
    new_session_response = client.get("/api/auth/me")
    assert new_session_response.status_code == 200


def test_change_email_requires_login(client, db_session):
    response = client.post(
        "/api/auth/change-email",
        json={"new_email": "new@example.com", "current_password": "x"},
    )
    assert response.status_code == 401


def test_change_email_rejects_wrong_password(client, db_session, monkeypatch):
    monkeypatch.setattr("app.routers.auth.send_email_change_confirmation", lambda **kwargs: None)
    _make_user(db_session)
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})
    response = client.post(
        "/api/auth/change-email",
        json={"new_email": "new@example.com", "current_password": "wrong"},
    )
    assert response.status_code == 401


def test_change_email_rejects_already_taken_address(client, db_session, monkeypatch):
    monkeypatch.setattr("app.routers.auth.send_email_change_confirmation", lambda **kwargs: None)
    _make_user(db_session)
    _make_user(db_session, email="taken@example.com", password="Other123!")
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})
    response = client.post(
        "/api/auth/change-email",
        json={"new_email": "taken@example.com", "current_password": "Grindcore123!"},
    )
    assert response.status_code == 409


def test_change_email_does_not_change_email_immediately(client, db_session, monkeypatch):
    monkeypatch.setattr("app.routers.auth.send_email_change_confirmation", lambda **kwargs: None)
    _make_user(db_session)
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})
    response = client.post(
        "/api/auth/change-email",
        json={"new_email": "new@example.com", "current_password": "Grindcore123!"},
    )
    assert response.status_code == 204

    me = client.get("/api/auth/me").json()
    assert me["email"] == "basti@example.com"  # noch unverändert


def test_confirm_email_change_updates_email_with_valid_token(client, db_session, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.routers.auth.send_email_change_confirmation",
        lambda **kwargs: sent.append(kwargs),
    )
    _make_user(db_session)
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})
    client.post(
        "/api/auth/change-email",
        json={"new_email": "new@example.com", "current_password": "Grindcore123!"},
    )
    assert len(sent) == 1
    confirm_url = sent[0]["confirm_url"]
    token = confirm_url.split("token=")[1]

    response = client.get(f"/api/auth/confirm-email-change?token={token}")
    assert response.status_code == 200
    assert response.json()["new_email"] == "new@example.com"

    me = client.get("/api/auth/me").json()
    assert me["email"] == "new@example.com"


def test_confirm_email_change_rejects_invalid_token(client, db_session):
    response = client.get("/api/auth/confirm-email-change?token=garbage")
    assert response.status_code == 400


def test_confirm_email_change_rejects_already_used_token(client, db_session, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.routers.auth.send_email_change_confirmation",
        lambda **kwargs: sent.append(kwargs),
    )
    _make_user(db_session)
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})
    client.post(
        "/api/auth/change-email",
        json={"new_email": "new@example.com", "current_password": "Grindcore123!"},
    )
    token = sent[0]["confirm_url"].split("token=")[1]

    first = client.get(f"/api/auth/confirm-email-change?token={token}")
    assert first.status_code == 200
    second = client.get(f"/api/auth/confirm-email-change?token={token}")
    assert second.status_code == 400


def test_change_email_invalidates_previous_pending_token(client, db_session, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.routers.auth.send_email_change_confirmation",
        lambda **kwargs: sent.append(kwargs),
    )
    _make_user(db_session)
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})

    client.post(
        "/api/auth/change-email",
        json={"new_email": "first@example.com", "current_password": "Grindcore123!"},
    )
    first_token = sent[0]["confirm_url"].split("token=")[1]

    # create_email_token signs {user_id, purpose} with second-resolution
    # itsdangerous timestamps and no other entropy, so two requests within
    # the same wall-clock second for the same user/purpose would otherwise
    # produce byte-identical tokens - sleep past the second boundary so the
    # two tokens in this test are actually distinct.
    import time
    time.sleep(1.1)

    client.post(
        "/api/auth/change-email",
        json={"new_email": "second@example.com", "current_password": "Grindcore123!"},
    )
    second_token = sent[1]["confirm_url"].split("token=")[1]
    assert first_token != second_token

    stale_response = client.get(f"/api/auth/confirm-email-change?token={first_token}")
    assert stale_response.status_code == 400

    fresh_response = client.get(f"/api/auth/confirm-email-change?token={second_token}")
    assert fresh_response.status_code == 200
    assert fresh_response.json()["new_email"] == "second@example.com"
