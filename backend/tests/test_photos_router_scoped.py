from datetime import datetime, timezone

from app.models.user import User
from app.services.auth import hash_password


def _login_and_get_client(client, db_session, email="a@b.com", password="pw12345"):
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name="A",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.commit()
    client.post("/api/auth/login", json={"email": email, "password": password})
    created = client.post("/api/clients", json={"name": "Kunde"}).json()
    return created["id"]


def test_photos_list_scoped_to_client(client, db_session):
    client_id_a = _login_and_get_client(client, db_session, email="a@b.com", password="pw12345")
    response = client.get(f"/api/clients/{client_id_a}/photos")
    assert response.status_code == 200
    assert response.json() == []


def test_cannot_list_photos_of_foreign_client(client, db_session):
    client_id_a = _login_and_get_client(client, db_session, email="a@b.com", password="pw12345")
    client.post("/api/auth/logout")
    _login_and_get_client(client, db_session, email="c@d.com", password="pw67890")

    response = client.get(f"/api/clients/{client_id_a}/photos")
    assert response.status_code == 404


def test_sync_requires_client_ownership(client, db_session):
    client_id_a = _login_and_get_client(client, db_session, email="a@b.com", password="pw12345")
    client.post("/api/auth/logout")
    _login_and_get_client(client, db_session, email="c@d.com", password="pw67890")

    response = client.post(f"/api/clients/{client_id_a}/photos/sync")
    assert response.status_code == 404


def test_cannot_assign_photo_of_foreign_client(client, db_session):
    client_id_a = _login_and_get_client(client, db_session, email="a@b.com", password="pw12345")
    client.post("/api/auth/logout")
    _login_and_get_client(client, db_session, email="c@d.com", password="pw67890")

    response = client.post(
        f"/api/clients/{client_id_a}/photos/999/assign", json={"pose_id": 999}
    )
    assert response.status_code == 404


def test_cannot_change_pose_of_photo_of_foreign_client(client, db_session):
    client_id_a = _login_and_get_client(client, db_session, email="a@b.com", password="pw12345")
    client.post("/api/auth/logout")
    _login_and_get_client(client, db_session, email="c@d.com", password="pw67890")

    response = client.patch(
        f"/api/clients/{client_id_a}/photos/999/pose", json={"pose_id": 999}
    )
    assert response.status_code == 404


def test_cannot_delete_photo_of_foreign_client(client, db_session):
    client_id_a = _login_and_get_client(client, db_session, email="a@b.com", password="pw12345")
    client.post("/api/auth/logout")
    _login_and_get_client(client, db_session, email="c@d.com", password="pw67890")

    response = client.delete(f"/api/clients/{client_id_a}/photos/999")
    assert response.status_code == 404


def test_assign_photo_blocked_for_single_account_after_free_quota(client, db_session):
    from app.models.photo import Photo, ProcessingStatus
    from app.models.pose import Pose

    # Default account_type ist bereits SINGLE (siehe User-Modell).
    client_id = _login_and_get_client(client, db_session, email="single-quota@b.com")

    pose = Pose(client_id=client_id, name="Front", sort_order=0)
    db_session.add(pose)
    db_session.commit()

    photos = []
    for day in (1, 2, 3):
        photo = Photo(
            client_id=client_id,
            filename=f"p{day}.jpg",
            original_path=f"photos_incoming/{client_id}/p{day}.jpg",
            taken_at=datetime(2026, 1, day, 12, 0, 0),
            status=ProcessingStatus.UNPROCESSED,
        )
        db_session.add(photo)
        photos.append(photo)
    db_session.commit()
    for p in photos:
        db_session.refresh(p)

    # Erste 2 Fotos (je ein neuer Tag) sind kostenlos zuordenbar.
    r1 = client.post(f"/api/clients/{client_id}/photos/{photos[0].id}/assign", json={"pose_id": pose.id})
    r2 = client.post(f"/api/clients/{client_id}/photos/{photos[1].id}/assign", json={"pose_id": pose.id})
    assert r1.status_code == 200
    assert r2.status_code == 200

    # 3. neuer Tag -> blockiert.
    r3 = client.post(f"/api/clients/{client_id}/photos/{photos[2].id}/assign", json={"pose_id": pose.id})
    assert r3.status_code == 402


def test_assign_photo_sets_processed_status_and_day_log(client, db_session):
    from app.models.photo import Photo, ProcessingStatus
    from app.models.pose import Pose

    client_id = _login_and_get_client(client, db_session)

    pose = Pose(client_id=client_id, name="Front", sort_order=0)
    db_session.add(pose)
    db_session.commit()

    photo = Photo(
        client_id=client_id,
        filename="p1.jpg",
        original_path=f"photos_incoming/{client_id}/p1.jpg",
        taken_at=datetime(2026, 1, 1, 12, 0, 0),
        status=ProcessingStatus.UNPROCESSED,
    )
    db_session.add(photo)
    db_session.commit()
    db_session.refresh(photo)

    response = client.post(
        f"/api/clients/{client_id}/photos/{photo.id}/assign",
        json={"pose_id": pose.id},
    )
    assert response.status_code == 200
    body = response.json()
    # Kein echtes Bild auf Platte in diesem Test -> MediaPipe findet nichts,
    # Normalisierung schlägt fehl, aber die Zuordnung selbst muss trotzdem
    # durchgehen (bestehendes "best effort"-Verhalten, siehe Design-Spec).
    assert body["status"] == "normalization_failed"
    assert body["pose_id"] == pose.id

    day_logs = client.get(f"/api/clients/{client_id}/day-logs").json()
    assert len(day_logs) == 1
    assert day_logs[0]["date"] == "2026-01-01"


def test_assign_photo_accepts_comma_decimal_weight(client, db_session):
    from app.models.photo import Photo, ProcessingStatus
    from app.models.pose import Pose

    client_id = _login_and_get_client(client, db_session)

    pose = Pose(client_id=client_id, name="Front", sort_order=0)
    db_session.add(pose)
    db_session.commit()

    photo = Photo(
        client_id=client_id,
        filename="p1.jpg",
        original_path=f"photos_incoming/{client_id}/p1.jpg",
        taken_at=datetime(2026, 1, 1, 12, 0, 0),
        status=ProcessingStatus.UNPROCESSED,
    )
    db_session.add(photo)
    db_session.commit()
    db_session.refresh(photo)

    response = client.post(
        f"/api/clients/{client_id}/photos/{photo.id}/assign",
        json={"pose_id": pose.id, "weight_kg": "76,05"},
    )
    assert response.status_code == 200

    day_logs = client.get(f"/api/clients/{client_id}/day-logs").json()
    assert any(log["weight_kg"] == 76.05 for log in day_logs)
