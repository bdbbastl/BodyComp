"""
Transaktionaler E-Mail-Versand über Resend - siehe Design-Spec Abschnitt
"E-Mail-Versand (Resend)". Läuft synchron im Request; bei einem
Resend-Fehler soll der Aufrufer die Exception sehen und dem Nutzer eine
ehrliche Fehlermeldung zeigen, statt einen stillen Fehlschlag zu haben.

Sandbox-Modus (keine verifizierte Domain, siehe Design-Spec): Mails gehen
nur an die eigene, bei Resend verifizierte Test-Adresse - das ist eine
Resend-seitige Einschränkung, keine hier im Code abgebildete.
"""
import resend

from app.core.config import settings

resend.api_key = settings.resend_api_key


def _base_email_html(title: str, body_html: str) -> str:
    return f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto; color: #0b0f14;">
      <h1 style="font-size: 20px;">BodyComp <span style="color: #0891b2;">Tracker</span></h1>
      <h2 style="font-size: 16px;">{title}</h2>
      {body_html}
    </div>
    """


def send_verification_email(*, to: str, verify_url: str) -> None:
    html = _base_email_html(
        "Please confirm your email address",
        f"""
        <p>Click the link below to complete your registration:</p>
        <p><a href="{verify_url}">{verify_url}</a></p>
        <p style="color: #64748b; font-size: 13px;">This link is valid for 24 hours.</p>
        """,
    )
    resend.Emails.send({
        "from": settings.email_from_address,
        "to": [to],
        "subject": "Confirm your email address - BodyComp Tracker",
        "html": html,
    })


def send_password_reset_email(*, to: str, reset_url: str) -> None:
    html = _base_email_html(
        "Reset your password",
        f"""
        <p>Click the link below to set a new password:</p>
        <p><a href="{reset_url}">{reset_url}</a></p>
        <p style="color: #64748b; font-size: 13px;">This link is valid for 1 hour. If this
        wasn't you, you can safely ignore this email.</p>
        """,
    )
    resend.Emails.send({
        "from": settings.email_from_address,
        "to": [to],
        "subject": "Reset your password - BodyComp Tracker",
        "html": html,
    })


def send_email_change_confirmation(*, to: str, confirm_url: str) -> None:
    html = _base_email_html(
        "Confirm your new email address",
        f"""
        <p>Click the link below to confirm this as your new BodyComp Tracker
        login email:</p>
        <p><a href="{confirm_url}">{confirm_url}</a></p>
        <p style="color: #64748b; font-size: 13px;">This link is valid for 24 hours.
        If you didn't request this change, you can safely ignore this email -
        your login email stays unchanged.</p>
        """,
    )
    resend.Emails.send({
        "from": settings.email_from_address,
        "to": [to],
        "subject": "Confirm your new email address - BodyComp Tracker",
        "html": html,
    })


def send_checkin_submitted_email(*, to: str, client_name: str, checkins_url: str) -> None:
    html = _base_email_html(
        "New check-in submitted",
        f"""
        <p><strong>{client_name}</strong> just submitted a new check-in.</p>
        <p><a href="{checkins_url}">View it now</a></p>
        """,
    )
    resend.Emails.send({
        "from": settings.email_from_address,
        "to": [to],
        "subject": f"New check-in from {client_name} - BodyComp Tracker",
        "html": html,
    })


def send_checkin_reviewed_email(
    *,
    to: str,
    coach_feedback_text: str | None,
    coach_feedback_video_url: str | None,
    checkin_url: str,
) -> None:
    feedback_html = (
        f'<p style="white-space: pre-wrap;">{coach_feedback_text}</p>'
        if coach_feedback_text
        else ""
    )
    video_html = (
        f'<p><a href="{coach_feedback_video_url}">Watch video feedback</a></p>'
        if coach_feedback_video_url
        else ""
    )
    html = _base_email_html(
        "Your check-in has feedback",
        f"""
        <p>Your coach reviewed your check-in and left feedback.</p>
        {feedback_html}
        {video_html}
        <p><a href="{checkin_url}">Open your check-in</a></p>
        """,
    )
    resend.Emails.send({
        "from": settings.email_from_address,
        "to": [to],
        "subject": "Your coach left feedback on your check-in - BodyComp Tracker",
        "html": html,
    })


def send_checkin_reminder_email(*, to: str, checkin_url: str) -> None:
    html = _base_email_html(
        "Time for your next check-in",
        f"""
        <p>Your coach is waiting for your next check-in - submit it here:</p>
        <p><a href="{checkin_url}">{checkin_url}</a></p>
        """,
    )
    resend.Emails.send({
        "from": settings.email_from_address,
        "to": [to],
        "subject": "Time for your check-in - BodyComp Tracker",
        "html": html,
    })


def send_welcome_email(*, to: str, display_name: str) -> None:
    html = _base_email_html(
        f"Welcome, {display_name}!",
        """
        <p>Your account is verified and ready to go.</p>
        <p><a href="{app_url}">Open BodyComp Tracker</a></p>
        """.replace("{app_url}", settings.frontend_base_url),
    )
    resend.Emails.send({
        "from": settings.email_from_address,
        "to": [to],
        "subject": "Welcome to BodyComp Tracker",
        "html": html,
    })


def send_trial_ending_email(*, to: str, days_left: int, plan_name: str) -> None:
    day_word = "day" if days_left == 1 else "days"
    html = _base_email_html(
        "Your trial is ending soon",
        f"""
        <p>Your {plan_name} trial ends in {days_left} {day_word}. Add a payment method to
        keep your subscription active without interruption.</p>
        <p><a href="{settings.frontend_base_url}/account">Manage your subscription</a></p>
        """,
    )
    resend.Emails.send({
        "from": settings.email_from_address,
        "to": [to],
        "subject": "Your trial is ending soon - BodyComp Tracker",
        "html": html,
    })


def send_quota_warning_email(*, to: str) -> None:
    html = _base_email_html(
        "1 free check-in left",
        f"""
        <p>You've used your first free check-in. You have <strong>1 free check-in left</strong>
        before you'll need to subscribe to keep tracking.</p>
        <p><a href="{settings.frontend_base_url}/account">See plans</a></p>
        """,
    )
    resend.Emails.send({
        "from": settings.email_from_address,
        "to": [to],
        "subject": "1 free check-in left - BodyComp Tracker",
        "html": html,
    })
