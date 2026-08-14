from datetime import datetime, timezone

from app.models.client import Client
from app.models.user import User
from app.services.auth import hash_password


def _login_as(client, db_session, email="basti@example.com", password="Pass123456!"):
    user = User(
        email=email, password_hash=hash_password(password), display_name="Basti",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.flush()
    # Normaler Signup legt via services/account.create_account automatisch
    # einen Client an - hier direkt nachgebildet, da der Test User() ohne
    # den Service-Weg instanziiert.
    db_session.add(Client(owner_id=user.id, name=user.display_name))
    db_session.commit()
    client.post("/api/auth/login", json={"email": email, "password": password})
    return user


def test_delete_account_requires_correct_password(client, db_session):
    _login_as(client, db_session)
    response = client.request("DELETE", "/api/auth/me", json={"password": "wrong"})
    assert response.status_code == 401


def test_delete_account_removes_user_and_clients(client, db_session):
    user = _login_as(client, db_session)
    user_id = user.id

    response = client.request("DELETE", "/api/auth/me", json={"password": "Pass123456!"})
    assert response.status_code == 204

    assert db_session.query(User).filter(User.id == user_id).first() is None
    assert db_session.query(Client).filter(Client.owner_id == user_id).count() == 0

    me_response = client.get("/api/auth/me")
    assert me_response.status_code == 401


def test_delete_google_only_account_without_password(client, db_session):
    google_user = User(
        email="google@example.com", display_name="G", google_id="sub-1",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(google_user)
    db_session.commit()

    from app.services.auth import create_session_token
    token = create_session_token(google_user.id)
    client.cookies.set("session", token)

    response = client.request("DELETE", "/api/auth/me", json={})
    assert response.status_code == 204
    assert db_session.query(User).filter(User.id == google_user.id).first() is None


def test_export_returns_user_and_client_data(client, db_session):
    _login_as(client, db_session)
    response = client.get("/api/auth/me/export")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "basti@example.com"
    assert len(body["clients"]) == 1
    assert body["clients"][0]["name"] == "Basti"
    assert "password_hash" not in body
