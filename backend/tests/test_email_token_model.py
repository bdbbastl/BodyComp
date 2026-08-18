from datetime import datetime, timedelta, timezone

from app.models.email_token import EmailToken, EmailTokenPurpose
from app.models.user import User
from app.services.auth import hash_password


def test_email_token_supports_change_email_purpose_with_new_email(db_session):
    user = User(
        email="old@example.com",
        password_hash=hash_password("Grindcore123!"),
        display_name="Basti",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    token = EmailToken(
        user_id=user.id,
        token_hash="deadbeef",
        purpose=EmailTokenPurpose.CHANGE_EMAIL,
        new_email="new@example.com",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db_session.add(token)
    db_session.commit()
    db_session.refresh(token)

    assert token.purpose == EmailTokenPurpose.CHANGE_EMAIL
    assert token.new_email == "new@example.com"
