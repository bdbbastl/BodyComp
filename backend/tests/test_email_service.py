from unittest.mock import MagicMock, patch

from app.services.email import send_verification_email, send_password_reset_email


def test_send_verification_email_calls_resend_with_correct_recipient():
    with patch("app.services.email.resend.Emails.send") as mock_send:
        mock_send.return_value = {"id": "fake-id"}
        send_verification_email(to="user@example.com", verify_url="https://app.example.com/verify-email?token=abc")

    assert mock_send.call_count == 1
    call_kwargs = mock_send.call_args[0][0]
    assert call_kwargs["to"] == ["user@example.com"]
    assert "verify-email?token=abc" in call_kwargs["html"]


def test_send_password_reset_email_calls_resend_with_correct_recipient():
    with patch("app.services.email.resend.Emails.send") as mock_send:
        mock_send.return_value = {"id": "fake-id"}
        send_password_reset_email(to="user@example.com", reset_url="https://app.example.com/reset-password?token=xyz")

    assert mock_send.call_count == 1
    call_kwargs = mock_send.call_args[0][0]
    assert call_kwargs["to"] == ["user@example.com"]
    assert "reset-password?token=xyz" in call_kwargs["html"]
