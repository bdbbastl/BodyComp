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
        "Bitte bestätige deine E-Mail-Adresse",
        f"""
        <p>Klicke auf den folgenden Link, um deine Registrierung abzuschließen:</p>
        <p><a href="{verify_url}">{verify_url}</a></p>
        <p style="color: #64748b; font-size: 13px;">Der Link ist 24 Stunden gültig.</p>
        """,
    )
    resend.Emails.send({
        "from": settings.email_from_address,
        "to": [to],
        "subject": "Bestätige deine E-Mail-Adresse - BodyComp Tracker",
        "html": html,
    })


def send_password_reset_email(*, to: str, reset_url: str) -> None:
    html = _base_email_html(
        "Passwort zurücksetzen",
        f"""
        <p>Klicke auf den folgenden Link, um ein neues Passwort zu setzen:</p>
        <p><a href="{reset_url}">{reset_url}</a></p>
        <p style="color: #64748b; font-size: 13px;">Der Link ist 1 Stunde gültig. Falls du das
        nicht warst, kannst du diese Mail ignorieren.</p>
        """,
    )
    resend.Emails.send({
        "from": settings.email_from_address,
        "to": [to],
        "subject": "Passwort zurücksetzen - BodyComp Tracker",
        "html": html,
    })


def send_checkin_submitted_email(*, to: str, client_name: str, checkins_url: str) -> None:
    html = _base_email_html(
        "Neuer Check-in eingereicht",
        f"""
        <p><strong>{client_name}</strong> hat gerade einen neuen Check-in eingereicht.</p>
        <p><a href="{checkins_url}">Jetzt ansehen</a></p>
        """,
    )
    resend.Emails.send({
        "from": settings.email_from_address,
        "to": [to],
        "subject": f"Neuer Check-in von {client_name} - BodyComp Tracker",
        "html": html,
    })
