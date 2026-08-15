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


def test_get_checkin_page_by_valid_token(client, db_session):
    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    token = created["checkin_token"]

    response = client.get(f"/api/public/checkin/{token}")
    assert response.status_code == 200
    body = response.json()
    assert body["client_name"] == "Max"
    assert body["submissions"] == []


def test_get_checkin_page_includes_submission_history(client, db_session):
    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    token = created["checkin_token"]

    submission = CheckinSubmission(
        client_id=created["id"],
        weight_kg=82.5,
        client_note="Fühle mich gut",
        status=CheckinStatus.REVIEWED,
        coach_feedback_text="Weiter so!",
        coach_feedback_video_url="https://loom.com/share/abc",
    )
    db_session.add(submission)
    db_session.commit()

    response = client.get(f"/api/public/checkin/{token}")
    body = response.json()
    assert len(body["submissions"]) == 1
    assert body["submissions"][0]["weight_kg"] == 82.5
    assert body["submissions"][0]["coach_feedback_text"] == "Weiter so!"


def test_get_checkin_page_with_invalid_token_returns_404(client, db_session):
    response = client.get("/api/public/checkin/does-not-exist")
    assert response.status_code == 404
