from unittest.mock import MagicMock, patch

from app.services.email import (
    send_admin_message_email,
    send_verification_email,
    send_password_reset_email,
    send_quota_warning_email,
    send_trial_ending_email,
    send_welcome_email,
)


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


def test_send_welcome_email_calls_resend_with_correct_subject():
    with patch("app.services.email.resend.Emails.send") as mock_send:
        mock_send.return_value = {"id": "fake-id"}
        send_welcome_email(to="max@example.com", display_name="Max")

    assert mock_send.call_count == 1
    call_kwargs = mock_send.call_args[0][0]
    assert call_kwargs["to"] == ["max@example.com"]
    assert "Welcome" in call_kwargs["subject"]


def test_send_trial_ending_email_includes_days_left():
    with patch("app.services.email.resend.Emails.send") as mock_send:
        mock_send.return_value = {"id": "fake-id"}
        send_trial_ending_email(to="coach@example.com", days_left=3, plan_name="Pro")

    assert mock_send.call_count == 1
    call_kwargs = mock_send.call_args[0][0]
    assert "3 days" in call_kwargs["html"]
    assert "Pro" in call_kwargs["html"]


def test_send_quota_warning_email_calls_resend():
    with patch("app.services.email.resend.Emails.send") as mock_send:
        mock_send.return_value = {"id": "fake-id"}
        send_quota_warning_email(to="single@example.com")

    assert mock_send.call_count == 1
    call_kwargs = mock_send.call_args[0][0]
    assert call_kwargs["to"] == ["single@example.com"]


def test_send_admin_message_email_escapes_html():
    with patch("app.services.email.resend.Emails.send") as mock_send:
        mock_send.return_value = {"id": "fake-id"}
        send_admin_message_email(
            to="user@example.com", message="<script>alert(1)</script>\nline2"
        )

    assert mock_send.call_count == 1
    call_kwargs = mock_send.call_args[0][0]
    assert call_kwargs["to"] == ["user@example.com"]
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in call_kwargs["html"]
    assert "<script>" not in call_kwargs["html"]
    assert "<br>line2" in call_kwargs["html"]
