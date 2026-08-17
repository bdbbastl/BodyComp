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
