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


def test_list_clients_includes_photo_count_and_last_activity(client, db_session):
    from datetime import date, datetime

    from app.models.photo import Photo, ProcessingStatus

    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()

    db_session.add(Photo(
        client_id=created["id"],
        filename="a.jpg",
        original_path="photos_processed/1/2026-01-01/a.jpg",
        taken_at=datetime(2026, 1, 1, 12, 0, 0),
        status=ProcessingStatus.PROCESSED,
    ))
    db_session.add(Photo(
        client_id=created["id"],
        filename="b.jpg",
        original_path="photos_processed/1/2026-02-01/b.jpg",
        taken_at=datetime(2026, 2, 1, 12, 0, 0),
        status=ProcessingStatus.PROCESSED,
    ))
    db_session.commit()

    list_resp = client.get("/api/clients")
    body = list_resp.json()
    assert body[0]["photo_count"] == 2
    assert body[0]["last_activity"] == "2026-02-01"


def test_list_clients_last_activity_is_null_without_photos(client, db_session):
    _login(client, db_session)
    client.post("/api/clients", json={"name": "Max"})

    body = client.get("/api/clients").json()
    assert body[0]["photo_count"] == 0
    assert body[0]["last_activity"] is None


def test_new_client_gets_a_checkin_token(client, db_session):
    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    assert created["checkin_token"]
    assert len(created["checkin_token"]) >= 20


def test_client_update_can_set_coach_private_note_email_and_reminder_days(client, db_session):
    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    updated = client.patch(
        f"/api/clients/{created['id']}",
        json={
            "coach_private_note": "Knieprobleme, langsam steigern",
            "email": "max@example.com",
            "checkin_reminder_days": 3,
        },
    ).json()
    assert updated["coach_private_note"] == "Knieprobleme, langsam steigern"
    assert updated["email"] == "max@example.com"
    assert updated["checkin_reminder_days"] == 3


def test_regenerate_checkin_token_changes_token(client, db_session):
    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    old_token = created["checkin_token"]

    response = client.post(f"/api/clients/{created['id']}/checkin-token/regenerate")
    assert response.status_code == 200
    new_token = response.json()["checkin_token"]
    assert new_token != old_token

    # Alter Link ist danach ungültig.
    old_link_check = client.get(f"/api/public/checkin/{old_token}")
    assert old_link_check.status_code == 404


def test_list_clients_includes_pending_checkins_count(client, db_session):
    from app.models.checkin_submission import CheckinStatus, CheckinSubmission

    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()

    db_session.add(CheckinSubmission(client_id=created["id"], status=CheckinStatus.PENDING))
    db_session.add(CheckinSubmission(client_id=created["id"], status=CheckinStatus.PENDING))
    db_session.add(CheckinSubmission(client_id=created["id"], status=CheckinStatus.REVIEWED))
    db_session.commit()

    response = client.get("/api/clients")
    body = response.json()
    match = next(c for c in body if c["id"] == created["id"])
    assert match["pending_checkins_count"] == 2


def test_create_client_blocked_when_over_billing_limit(client, db_session):
    _login(client, db_session)
    # UNSUBSCRIBED_CLIENT_LIMIT ist 1: der erste Client darf noch
    # angelegt werden, der zweite (ohne aktives Abo) muss blockiert sein.
    first = client.post("/api/clients", json={"name": "Erster Klient"})
    assert first.status_code == 201
    response = client.post("/api/clients", json={"name": "Zweiter Klient"})
    assert response.status_code == 402


def test_delete_client_removes_client_and_cascades(client, db_session, tmp_path, monkeypatch):
    from app.core.config import settings
    from app.models.client import Client
    from app.models.photo import Photo, ProcessingStatus
    from app.models.pose import Pose

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    _login(client, db_session)

    create_resp = client.post("/api/clients", json={"name": "To Delete"})
    client_id = create_resp.json()["id"]

    client_row = db_session.get(Client, client_id)
    pose = Pose(client_id=client_id, name="Front", sort_order=0)
    db_session.add(pose)
    db_session.commit()
    db_session.refresh(pose)

    photo_dir = tmp_path / "photos_processed" / str(client_id)
    photo_dir.mkdir(parents=True)
    photo_file = photo_dir / "a.jpg"
    photo_file.write_bytes(b"fake-jpeg-bytes")
    photo = Photo(
        client_id=client_id,
        filename="a.jpg",
        original_path=f"photos_processed/{client_id}/a.jpg",
        taken_at=datetime.now(timezone.utc),
        status=ProcessingStatus.PROCESSED,
        pose_id=pose.id,
    )
    db_session.add(photo)
    db_session.commit()
    photo_id = photo.id
    pose_id = pose.id

    response = client.delete(f"/api/clients/{client_id}")
    assert response.status_code == 204

    assert db_session.get(Client, client_id) is None
    assert not photo_file.exists()

    from app.models.photo import Photo as PhotoModel
    from app.models.pose import Pose as PoseModel

    db_session.expunge_all()
    assert db_session.get(PhotoModel, photo_id) is None
    assert db_session.get(PoseModel, pose_id) is None

    list_resp = client.get("/api/clients")
    assert list_resp.json() == []


def test_delete_client_requires_ownership(client, db_session):
    owner_a = _login(client, db_session, email="owner-a@example.com", password="pw12345")
    create_resp = client.post("/api/clients", json={"name": "Owner A's Client"})
    client_id = create_resp.json()["id"]

    client.post("/api/auth/logout")
    _login(client, db_session, email="owner-b@example.com", password="pw12345")
    response = client.delete(f"/api/clients/{client_id}")
    assert response.status_code == 404
