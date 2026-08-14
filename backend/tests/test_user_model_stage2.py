from datetime import datetime, timedelta, timezone

from app.models.email_token import EmailToken, EmailTokenPurpose
from app.models.user import User


def test_user_can_be_created_without_password(db_session):
    """Google-only-Accounts haben kein Passwort."""
    user = User(email="google@example.com", display_name="Google User", google_id="google-sub-123")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    assert user.password_hash is None
    assert user.email_verified_at is None
    assert user.privacy_accepted_at is None
    assert user.sessions_invalidated_at is None


def test_user_google_id_is_unique(db_session):
    from sqlalchemy.exc import IntegrityError
    import pytest

    db_session.add(User(email="a@b.com", display_name="A", google_id="dup-sub"))
    db_session.commit()

    db_session.add(User(email="c@d.com", display_name="C", google_id="dup-sub"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_email_token_belongs_to_user_and_has_purpose(db_session):
    user = User(email="a@b.com", display_name="A", password_hash="x")
    db_session.add(user)
    db_session.flush()

    token = EmailToken(
        user_id=user.id,
        token_hash="abc123hash",
        purpose=EmailTokenPurpose.VERIFY_EMAIL,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db_session.add(token)
    db_session.commit()
    db_session.refresh(token)

    assert token.used_at is None
    assert token.purpose == EmailTokenPurpose.VERIFY_EMAIL


def test_email_token_deleted_when_user_deleted(db_session):
    user = User(email="a@b.com", display_name="A", password_hash="x")
    db_session.add(user)
    db_session.flush()
    db_session.add(EmailToken(
        user_id=user.id,
        token_hash="abc",
        purpose=EmailTokenPurpose.RESET_PASSWORD,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    ))
    db_session.commit()

    db_session.delete(user)
    db_session.commit()

    assert db_session.query(EmailToken).count() == 0
