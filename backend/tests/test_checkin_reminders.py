from datetime import datetime, timedelta, timezone

from app.models.checkin_submission import CheckinSubmission
from app.models.client import Client
from app.models.user import User
from app.services.auth import hash_password
from app.services.checkin_reminders import run_checkin_reminders


def _make_user_and_client(db_session, **client_kwargs):
    user = User(
        email="coach@example.com",
        password_hash=hash_password("pw12345"),
        display_name="Coach",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.flush()
    client_row = Client(owner_id=user.id, name="Max", **client_kwargs)
    db_session.add(client_row)
    db_session.commit()
    db_session.refresh(client_row)
    return user, client_row


def test_sends_reminder_when_no_submission_ever_and_threshold_passed(db_session, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.checkin_reminders.send_checkin_reminder_email",
        lambda **kwargs: sent.append(kwargs),
    )

    _, client_row = _make_user_and_client(
        db_session, email="max@example.com", checkin_reminder_days=7
    )
    client_row.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    db_session.commit()

    count = run_checkin_reminders(db_session)

    assert count == 1
    assert sent[0]["to"] == "max@example.com"


def test_no_reminder_when_checkin_reminder_days_not_set(db_session, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.checkin_reminders.send_checkin_reminder_email",
        lambda **kwargs: sent.append(kwargs),
    )
    _, client_row = _make_user_and_client(db_session, email="max@example.com")
    client_row.created_at = datetime.now(timezone.utc) - timedelta(days=30)
    db_session.commit()

    assert run_checkin_reminders(db_session) == 0
    assert sent == []


def test_no_reminder_when_no_email_on_file(db_session, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.checkin_reminders.send_checkin_reminder_email",
        lambda **kwargs: sent.append(kwargs),
    )
    _, client_row = _make_user_and_client(db_session, checkin_reminder_days=7)
    client_row.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    db_session.commit()

    assert run_checkin_reminders(db_session) == 0
    assert sent == []


def test_no_reminder_when_recent_submission_exists(db_session, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.checkin_reminders.send_checkin_reminder_email",
        lambda **kwargs: sent.append(kwargs),
    )
    _, client_row = _make_user_and_client(
        db_session, email="max@example.com", checkin_reminder_days=7
    )
    db_session.add(CheckinSubmission(
        client_id=client_row.id,
        submitted_at=datetime.now(timezone.utc) - timedelta(days=1),
    ))
    db_session.commit()

    assert run_checkin_reminders(db_session) == 0
    assert sent == []


def test_no_duplicate_reminder_within_the_same_window(db_session, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.checkin_reminders.send_checkin_reminder_email",
        lambda **kwargs: sent.append(kwargs),
    )
    _, client_row = _make_user_and_client(
        db_session, email="max@example.com", checkin_reminder_days=7
    )
    client_row.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    client_row.last_reminder_sent_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()

    assert run_checkin_reminders(db_session) == 0
    assert sent == []
