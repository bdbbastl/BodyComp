from app.models.user import User
from app.services.auth import hash_password


def _login_and_get_client(client, db_session, email="a@b.com", password="pw12345"):
    user = User(email=email, password_hash=hash_password(password), display_name="A")
    db_session.add(user)
    db_session.commit()
    client.post("/api/auth/login", json={"email": email, "password": password})
    created = client.post("/api/clients", json={"name": "Kunde"}).json()
    return created["id"]


def test_poses_are_scoped_to_client(client, db_session):
    client_id_a = _login_and_get_client(client, db_session, email="a@b.com", password="pw12345")
    poses_a = client.get(f"/api/clients/{client_id_a}/poses").json()
    assert len(poses_a) == 7  # Default-Seed
    client.post("/api/auth/logout")

    client_id_b = _login_and_get_client(client, db_session, email="c@d.com", password="pw67890")
    poses_b = client.get(f"/api/clients/{client_id_b}/poses").json()
    assert len(poses_b) == 7
    assert poses_a[0]["id"] != poses_b[0]["id"]


def test_cannot_list_poses_of_foreign_client(client, db_session):
    client_id_a = _login_and_get_client(client, db_session, email="a@b.com", password="pw12345")
    client.post("/api/auth/logout")
    _login_and_get_client(client, db_session, email="c@d.com", password="pw67890")

    response = client.get(f"/api/clients/{client_id_a}/poses")
    assert response.status_code == 404


def test_create_pose_scoped_to_client(client, db_session):
    client_id = _login_and_get_client(client, db_session)
    response = client.post(
        f"/api/clients/{client_id}/poses", json={"name": "Custom Pose"}
    )
    assert response.status_code == 201
    poses = client.get(f"/api/clients/{client_id}/poses").json()
    assert any(p["name"] == "Custom Pose" for p in poses)
