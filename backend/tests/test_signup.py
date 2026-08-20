from unittest.mock import patch

from app.models.email_token import EmailToken, EmailTokenPurpose
from app.models.user import User


def test_signup_creates_unverified_user_and_sends_email(client, db_session):
    with patch("app.routers.auth.send_verification_email") as mock_send:
        response = client.post(
            "/api/auth/signup",
            json={
                "email": "new@example.com",
                "password": "SuperSecret123!",
                "display_name": "New User",
                "privacy_accepted": True,
            },
        )
    assert response.status_code == 201
    assert mock_send.call_count == 1

    user = db_session.query(User).filter(User.email == "new@example.com").first()
    assert user is not None
    assert user.email_verified_at is None
    assert user.privacy_accepted_at is not None

    token_row = db_session.query(EmailToken).filter(EmailToken.user_id == user.id).first()
    assert token_row.purpose == EmailTokenPurpose.VERIFY_EMAIL
    assert token_row.used_at is None


def test_signup_rolls_back_account_when_verification_email_fails(client, db_session):
    """Regressionstest: schlug der Bestätigungsmail-Versand fehl (z.B.
    Resend-Konfigurationsproblem wie in Produktion/Staging gesehen -
    onboarding@resend.dev als Sandbox-Absender kann nicht an echte
    Adressen zustellen), blieb bisher ein verwaister, unverifizierter
    Account zurück, der jeden erneuten Signup-Versuch mit derselben
    Adresse mit 409 blockierte, obwohl der Nutzer nie eine Mail bekam."""
    with patch("app.routers.auth.send_verification_email", side_effect=Exception("Resend failed")):
        response = client.post(
            "/api/auth/signup",
            json={
                "email": "orphan@example.com",
                "password": "SuperSecret123!",
                "display_name": "Orphan",
                "privacy_accepted": True,
            },
        )
    assert response.status_code == 503

    # Kein verwaister Account - ein erneuter Versuch muss möglich sein.
    assert db_session.query(User).filter(User.email == "orphan@example.com").first() is None

    with patch("app.routers.auth.send_verification_email") as mock_send:
        retry_response = client.post(
            "/api/auth/signup",
            json={
                "email": "orphan@example.com",
                "password": "SuperSecret123!",
                "display_name": "Orphan",
                "privacy_accepted": True,
            },
        )
    assert retry_response.status_code == 201
    assert mock_send.call_count == 1


def test_signup_without_privacy_consent_is_rejected(client, db_session):
    response = client.post(
        "/api/auth/signup",
        json={
            "email": "new@example.com",
            "password": "SuperSecret123!",
            "display_name": "New User",
            "privacy_accepted": False,
        },
    )
    assert response.status_code == 422


def test_signup_with_duplicate_email_fails(client, db_session):
    with patch("app.routers.auth.send_verification_email"):
        client.post(
            "/api/auth/signup",
            json={"email": "dup@example.com", "password": "SuperSecret123!", "display_name": "A", "privacy_accepted": True},
        )
        response = client.post(
            "/api/auth/signup",
            json={"email": "dup@example.com", "password": "AnotherPass123!", "display_name": "B", "privacy_accepted": True},
        )
    assert response.status_code == 409


def test_signup_rejects_short_password(client, db_session):
    response = client.post(
        "/api/auth/signup",
        json={"email": "new@example.com", "password": "short", "display_name": "New User", "privacy_accepted": True},
    )
    assert response.status_code == 422


def test_login_before_verification_is_rejected(client, db_session):
    with patch("app.routers.auth.send_verification_email"):
        client.post(
            "/api/auth/signup",
            json={"email": "unverified@example.com", "password": "SuperSecret123!", "display_name": "A", "privacy_accepted": True},
        )
    response = client.post(
        "/api/auth/login", json={"email": "unverified@example.com", "password": "SuperSecret123!"}
    )
    assert response.status_code == 403
    assert "verify" in response.json()["detail"].lower()  # "Please verify your email address first"
