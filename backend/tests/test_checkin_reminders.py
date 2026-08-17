from datetime import datetime, timedelta, timezone

from app.models.checkin_submission import CheckinSubmission
from app.models.client import Client
from app.models.user import AccountType, User
from app.services.auth import hash_password
from app.services.checkin_reminders import run_checkin_reminders


def _make_user_and_client(db_session, account_type=AccountType.COACH, **client_kwargs):
    user = User(
        email="coach@example.com",
        password_hash=hash_password("pw12345"),
        display_name="Coach",
        email_verified_at=datetime.now(timezone.utc),
        account_type=account_type,
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


def test_uses_owner_email_as_fallback_for_single_account_without_client_email(db_session, monkeypatch):
    """Regression fuer das UX-Feedback vom 2026-08-17: bei Single-Accounts
    ist der 'Klient' der User selbst - keine separate Klienten-E-Mail
    noetig, die Account-E-Mail des Owners reicht als Ziel."""
    sent = []
    monkeypatch.setattr(
        "app.services.checkin_reminders.send_checkin_reminder_email",
        lambda **kwargs: sent.append(kwargs),
    )
    user, client_row = _make_user_and_client(
        db_session, account_type=AccountType.SINGLE, checkin_reminder_days=7
    )
    client_row.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    db_session.commit()

    count = run_checkin_reminders(db_session)

    assert count == 1
    assert sent[0]["to"] == user.email


def test_coach_client_without_email_gets_no_reminder_even_if_owner_has_email(db_session, monkeypatch):
    """Der Fallback auf die Owner-E-Mail gilt NUR fuer Single-Accounts -
    bei Coaches waere die eigene Adresse keine sinnvolle Erinnerung fuer
    einen echten Klienten."""
    sent = []
    monkeypatch.setattr(
        "app.services.checkin_reminders.send_checkin_reminder_email",
        lambda **kwargs: sent.append(kwargs),
    )
    _, client_row = _make_user_and_client(
        db_session, account_type=AccountType.COACH, checkin_reminder_days=7
    )
    client_row.created_at = datetime.now(timezone.utc) - timedelta(days=10)
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
