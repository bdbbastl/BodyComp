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
