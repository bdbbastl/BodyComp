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
    assert "oauth_state_session" in response.cookies


def test_google_login_does_not_overwrite_existing_login_session_cookie(client, db_session):
    """Regressionstest: SessionMiddleware nutzte früher denselben
    Cookie-Namen ("session") wie der App-eigene Login-Cookie - ein Klick
    auf "Mit Google anmelden" während man schon eingeloggt war, hat den
    Login-Cookie stillschweigend durch den OAuth-State-Cookie ersetzt und
    damit die bestehende Session zerstört."""
    user = User(
        email="basti@example.com",
        password_hash=hash_password("Grindcore123!"),
        display_name="Basti",
        email_verified_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    db_session.add(user)
    db_session.commit()

    login_resp = client.post(
        "/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"}
    )
    assert login_resp.status_code == 200
    login_session_cookie = client.cookies.get("session")
    assert login_session_cookie is not None

    client.get("/api/auth/google/login", follow_redirects=False)

    # Der Login-Cookie ("session") muss unverändert bleiben - nicht vom
    # OAuth-State-Cookie ("oauth_state_session") überschrieben worden sein.
    assert client.cookies.get("session") == login_session_cookie
    assert client.cookies.get("oauth_state_session") is not None

    me_response = client.get("/api/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "basti@example.com"


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


def test_google_callback_clears_password_when_linking_unverified_account(client, db_session):
    """Verhindert Account-Übernahme: ein Angreifer registriert die
    E-Mail-Adresse des Opfers per Signup mit einem selbstgewählten
    Passwort und lässt den Account unverifiziert (Login per Passwort
    bleibt so gesperrt). Wenn das Opfer sich später per Google mit
    derselben E-Mail-Adresse einloggt, ist Google die erste Partei,
    die den Besitz der Adresse tatsächlich nachweist - das vom
    Angreifer gesetzte Passwort muss deshalb ungültig gemacht werden."""
    attacker_password = "AttackerChosen123!"
    victim = User(
        email="google@example.com",
        display_name="Victim (pre-registered by attacker)",
        password_hash=hash_password(attacker_password),
        email_verified_at=None,  # nie verifiziert - der Angreifer hat den Link nie geklickt
    )
    db_session.add(victim)
    db_session.commit()
    victim_id = victim.id

    with patch("app.routers.auth.oauth.google.authorize_access_token", new_callable=AsyncMock) as mock_token:
        mock_token.return_value = {"userinfo": _fake_google_userinfo()}
        response = client.get("/api/auth/google/callback", follow_redirects=False)

    assert "session" in response.cookies
    db_session.refresh(victim)
    assert victim.id == victim_id
    assert db_session.query(User).count() == 1
    assert victim.google_id == "google-sub-123"
    assert victim.email_verified_at is not None
    assert victim.password_hash is None  # Angreifer-Passwort ist entwertet

    # Der Angreifer kann sich nicht mehr per Passwort einloggen.
    login_response = client.post(
        "/api/auth/login",
        json={"email": "google@example.com", "password": attacker_password},
    )
    assert login_response.status_code == 401


def test_google_callback_rejects_deactivated_existing_google_user(client, db_session):
    from datetime import datetime, timezone

    existing = User(
        email="google@example.com",
        display_name="Google User",
        google_id="google-sub-123",
        email_verified_at=datetime.now(timezone.utc),
        is_active=False,
    )
    db_session.add(existing)
    db_session.commit()

    with patch("app.routers.auth.oauth.google.authorize_access_token", new_callable=AsyncMock) as mock_token:
        mock_token.return_value = {"userinfo": _fake_google_userinfo()}
        response = client.get("/api/auth/google/callback", follow_redirects=False)

    assert response.status_code in (302, 307)
    assert "session" not in response.cookies
    assert "error=account_disabled" in response.headers["location"]


def test_google_callback_rejects_deactivated_account_without_mutating_it(client, db_session):
    """Regressionstest (Code-Review nach Task 2): ein deaktivierter
    Account, der über E-Mail+Passwort gefunden wird, darf NICHT verlinkt
    werden (kein google_id, kein entwertetes Passwort) - der Login muss
    komplett eingefroren bleiben, nicht nur die Session verweigert werden."""
    attacker_password = "AttackerChosen123!"
    victim = User(
        email="google@example.com",
        display_name="Deactivated Victim",
        password_hash=hash_password(attacker_password),
        email_verified_at=None,
        is_active=False,
    )
    db_session.add(victim)
    db_session.commit()
    victim_id = victim.id

    with patch("app.routers.auth.oauth.google.authorize_access_token", new_callable=AsyncMock) as mock_token:
        mock_token.return_value = {"userinfo": _fake_google_userinfo()}
        response = client.get("/api/auth/google/callback", follow_redirects=False)

    assert response.status_code in (302, 307)
    assert "session" not in response.cookies
    assert "error=account_disabled" in response.headers["location"]

    db_session.refresh(victim)
    assert victim.id == victim_id
    assert victim.google_id is None  # keine Verknüpfung stattgefunden
    assert victim.password_hash is not None  # Passwort nicht entwertet
    assert victim.email_verified_at is None  # keine Mutation stattgefunden
