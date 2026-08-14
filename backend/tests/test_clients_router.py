from app.models.user import User
from app.services.auth import hash_password


def _login(client, db_session, email="a@b.com", password="pw12345"):
    user = User(email=email, password_hash=hash_password(password), display_name="A")
    db_session.add(user)
    db_session.commit()
    client.post("/api/auth/login", json={"email": email, "password": password})
    return user


def test_create_and_list_clients(client, db_session):
    _login(client, db_session)

    create_resp = client.post(
        "/api/clients",
        json={"name": "Max Mustermann", "height_cm": 180, "birth_date": "1998-01-01", "gender": "männlich", "start_date": "2026-01-01"},
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["name"] == "Max Mustermann"
    assert created["height_cm"] == 180
    assert created["birth_date"] == "1998-01-01"

    list_resp = client.get("/api/clients")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


def test_cannot_see_other_users_clients(client, db_session):
    owner_a = _login(client, db_session, email="a@b.com", password="pw12345")
    resp = client.post("/api/clients", json={"name": "A's Kunde"})
    client_id = resp.json()["id"]
    client.post("/api/auth/logout")

    _login(client, db_session, email="c@d.com", password="pw67890")
    get_resp = client.get(f"/api/clients/{client_id}")
    assert get_resp.status_code == 404

    list_resp = client.get("/api/clients")
    assert list_resp.json() == []


def test_update_client_metrics(client, db_session):
    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()

    patch_resp = client.patch(f"/api/clients/{created['id']}", json={"height_cm": 185.5})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["height_cm"] == 185.5
    assert patch_resp.json()["name"] == "Max"


def test_unauthenticated_request_rejected(client, db_session):
    response = client.get("/api/clients")
    assert response.status_code == 401


def test_creating_client_seeds_default_poses(client, db_session):
    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()

    from app.models.pose import Pose

    poses = db_session.query(Pose).filter(Pose.client_id == created["id"]).order_by(Pose.sort_order).all()
    assert len(poses) == 7
    assert poses[0].name == "Front Double Biceps"
