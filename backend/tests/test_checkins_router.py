from datetime import datetime, timezone

from app.models.checkin_submission import CheckinStatus, CheckinSubmission
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


def test_list_checkins_returns_pending_first(client, db_session):
    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()

    db_session.add(CheckinSubmission(client_id=created["id"], status=CheckinStatus.REVIEWED))
    db_session.add(CheckinSubmission(client_id=created["id"], status=CheckinStatus.PENDING))
    db_session.commit()

    response = client.get(f"/api/clients/{created['id']}/checkins")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["status"] == "pending"


def test_list_checkins_for_foreign_client_returns_404(client, db_session):
    _login(client, db_session, email="a@b.com")
    created = client.post("/api/clients", json={"name": "Max"}).json()
    client.post("/api/auth/logout")

    _login(client, db_session, email="c@d.com")
    response = client.get(f"/api/clients/{created['id']}/checkins")
    assert response.status_code == 404


def test_update_checkin_sets_feedback_and_marks_reviewed(client, db_session):
    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()

    submission = CheckinSubmission(client_id=created["id"])
    db_session.add(submission)
    db_session.commit()
    db_session.refresh(submission)

    response = client.patch(
        f"/api/clients/{created['id']}/checkins/{submission.id}",
        json={
            "coach_feedback_text": "Sieht gut aus!",
            "coach_feedback_video_url": "https://loom.com/share/xyz",
            "mark_reviewed": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "reviewed"
    assert body["coach_feedback_text"] == "Sieht gut aus!"
    assert body["reviewed_at"] is not None


def test_update_checkin_not_found_returns_404(client, db_session):
    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()

    response = client.patch(
        f"/api/clients/{created['id']}/checkins/9999", json={"mark_reviewed": True}
    )
    assert response.status_code == 404


def test_delete_checkin_removes_submission_and_photos(client, db_session):
    from app.models.photo import Photo, ProcessingStatus
    from app.models.pose import Pose

    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    client_id = created["id"]

    pose = Pose(client_id=client_id, name="Front", sort_order=0)
    db_session.add(pose)
    db_session.commit()

    submission = CheckinSubmission(client_id=client_id, status=CheckinStatus.REVIEWED)
    db_session.add(submission)
    db_session.commit()
    db_session.refresh(submission)

    photo = Photo(
        client_id=client_id,
        filename="p1.jpg",
        original_path=f"photos_processed/{client_id}/p1_delete_test.jpg",
        taken_at=datetime(2026, 1, 1, 12, 0, 0),
        status=ProcessingStatus.PROCESSED,
        pose_id=pose.id,
        checkin_submission_id=submission.id,
    )
    db_session.add(photo)
    db_session.commit()
    photo_id = photo.id
    submission_id = submission.id

    response = client.delete(f"/api/clients/{client_id}/checkins/{submission_id}")
    assert response.status_code == 204

    assert db_session.query(CheckinSubmission).filter_by(id=submission_id).first() is None
    assert db_session.query(Photo).filter_by(id=photo_id).first() is None


def test_delete_checkin_leaves_day_log_untouched(client, db_session):
    from datetime import date as date_

    from app.models.day_log import DayLog

    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    client_id = created["id"]

    day_log = DayLog(client_id=client_id, date=date_(2026, 1, 1), weight_kg=80.0)
    db_session.add(day_log)
    submission = CheckinSubmission(
        client_id=client_id, status=CheckinStatus.REVIEWED, weight_kg=80.0
    )
    db_session.add(submission)
    db_session.commit()
    day_log_id = day_log.id
    submission_id = submission.id

    response = client.delete(f"/api/clients/{client_id}/checkins/{submission_id}")
    assert response.status_code == 204

    day_log_after = db_session.query(DayLog).filter_by(id=day_log_id).first()
    assert day_log_after is not None
    assert day_log_after.weight_kg == 80.0


def test_delete_checkin_404_for_unknown_id(client, db_session):
    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    response = client.delete(f"/api/clients/{created['id']}/checkins/999999")
    assert response.status_code == 404


def test_delete_checkin_404_for_foreign_client(client, db_session):
    _login(client, db_session, email="a@b.com")
    created = client.post("/api/clients", json={"name": "Max"}).json()
    submission = CheckinSubmission(client_id=created["id"], status=CheckinStatus.PENDING)
    db_session.add(submission)
    db_session.commit()
    submission_id = submission.id
    client.post("/api/auth/logout")

    _login(client, db_session, email="c@d.com")
    response = client.delete(f"/api/clients/{created['id']}/checkins/{submission_id}")
    assert response.status_code == 404
