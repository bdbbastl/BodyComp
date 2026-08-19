from datetime import datetime, timedelta, timezone

from app.models.checkin_submission import CheckinStatus, CheckinSubmission
from app.models.client import Client
from app.models.photo import Photo, ProcessingStatus
from app.models.user import User
from app.services.auth import hash_password


def _login(client, db_session, email="coach@b.com", password="pw12345"):
    user = db_session.query(User).filter(User.email == email).first()
    if user is None:
        user = User(
            email=email,
            password_hash=hash_password(password),
            display_name="Coach",
            email_verified_at=datetime.now(timezone.utc),
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
    client.post("/api/auth/login", json={"email": email, "password": password})
    return user


def test_coach_summary_requires_login(client, db_session):
    response = client.get("/api/dashboard/coach-summary")
    assert response.status_code == 401


def test_coach_summary_lists_pending_checkins_across_clients(client, db_session):
    user = _login(client, db_session)
    c1 = Client(owner_id=user.id, name="Client A")
    c2 = Client(owner_id=user.id, name="Client B")
    db_session.add_all([c1, c2])
    db_session.commit()
    db_session.refresh(c1)
    db_session.refresh(c2)

    older = CheckinSubmission(
        client_id=c1.id,
        weight_kg=80.0,
        status=CheckinStatus.PENDING,
        submitted_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    newer = CheckinSubmission(
        client_id=c2.id,
        weight_kg=70.0,
        status=CheckinStatus.PENDING,
        submitted_at=datetime.now(timezone.utc),
    )
    reviewed = CheckinSubmission(
        client_id=c1.id,
        weight_kg=81.0,
        status=CheckinStatus.REVIEWED,
        submitted_at=datetime.now(timezone.utc),
    )
    db_session.add_all([older, newer, reviewed])
    db_session.commit()

    response = client.get("/api/dashboard/coach-summary")
    assert response.status_code == 200
    body = response.json()
    pending = body["pending_checkins"]
    assert len(pending) == 2
    # neueste zuerst
    assert pending[0]["client_name"] == "Client B"
    assert pending[1]["client_name"] == "Client A"


def test_coach_summary_needs_attention_uses_seven_day_threshold(client, db_session):
    user = _login(client, db_session)
    quiet_client = Client(owner_id=user.id, name="Quiet Client")
    active_client = Client(owner_id=user.id, name="Active Client")
    never_active_client = Client(owner_id=user.id, name="Never Active")
    db_session.add_all([quiet_client, active_client, never_active_client])
    db_session.commit()
    db_session.refresh(quiet_client)
    db_session.refresh(active_client)

    old_photo = Photo(
        client_id=quiet_client.id,
        filename="old.jpg",
        original_path=f"photos_processed/{quiet_client.id}/old.jpg",
        taken_at=datetime.now(timezone.utc) - timedelta(days=8),
        status=ProcessingStatus.PROCESSED,
    )
    recent_photo = Photo(
        client_id=active_client.id,
        filename="recent.jpg",
        original_path=f"photos_processed/{active_client.id}/recent.jpg",
        taken_at=datetime.now(timezone.utc) - timedelta(days=1),
        status=ProcessingStatus.PROCESSED,
    )
    db_session.add_all([old_photo, recent_photo])
    db_session.commit()

    response = client.get("/api/dashboard/coach-summary")
    assert response.status_code == 200
    names = {entry["client_name"] for entry in response.json()["needs_attention"]}
    assert "Quiet Client" in names
    assert "Never Active" in names
    assert "Active Client" not in names


def test_coach_summary_week_stats_counts_recent_activity(client, db_session):
    user = _login(client, db_session)
    c1 = Client(owner_id=user.id, name="Client A")
    c2 = Client(owner_id=user.id, name="Client B")
    db_session.add_all([c1, c2])
    db_session.commit()
    db_session.refresh(c1)
    db_session.refresh(c2)

    recent_checkin = CheckinSubmission(
        client_id=c1.id,
        weight_kg=80.0,
        status=CheckinStatus.PENDING,
        submitted_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    old_checkin = CheckinSubmission(
        client_id=c1.id,
        weight_kg=79.0,
        status=CheckinStatus.REVIEWED,
        submitted_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    recent_photo = Photo(
        client_id=c2.id,
        filename="recent.jpg",
        original_path=f"photos_processed/{c2.id}/recent.jpg",
        taken_at=datetime.now(timezone.utc) - timedelta(days=3),
        status=ProcessingStatus.PROCESSED,
    )
    db_session.add_all([recent_checkin, old_checkin, recent_photo])
    db_session.commit()

    response = client.get("/api/dashboard/coach-summary")
    assert response.status_code == 200
    week_stats = response.json()["week_stats"]
    assert week_stats["checkins"] == 1
    assert week_stats["photos"] == 1
    assert week_stats["active_clients"] == 2


def test_coach_summary_scoped_to_own_clients_only(client, db_session):
    _login(client, db_session, email="coach1@b.com")
    client.post("/api/auth/logout")
    other = _login(client, db_session, email="coach2@b.com")
    other_client = Client(owner_id=other.id, name="Other Coach Client")
    db_session.add(other_client)
    db_session.commit()
    db_session.refresh(other_client)

    old_checkin = CheckinSubmission(
        client_id=other_client.id,
        weight_kg=80.0,
        status=CheckinStatus.PENDING,
        submitted_at=datetime.now(timezone.utc),
    )
    db_session.add(old_checkin)
    db_session.commit()

    client.post("/api/auth/logout")
    _login(client, db_session, email="coach1@b.com")
    response = client.get("/api/dashboard/coach-summary")
    assert response.status_code == 200
    assert response.json()["pending_checkins"] == []
