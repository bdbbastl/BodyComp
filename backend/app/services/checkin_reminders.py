"""
Erinnerungsmails an Klienten ohne aktuellen Check-in - siehe Design-Spec
Abschnitt "Benachrichtigungen". Reine, testbare Funktion (kein Scheduler-
Code hier) - siehe core/scheduler.py für die tägliche Cron-Anbindung.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.checkin_submission import CheckinSubmission
from app.models.client import Client
from app.models.user import AccountType
from app.services.email import send_checkin_reminder_email


def run_checkin_reminders(db: Session) -> int:
    """Prüft jeden Client mit `checkin_reminder_days` gesetzt UND einer
    erreichbaren E-Mail-Adresse: wurde seit der letzten Einreichung (oder
    seit Account-Erstellung, falls noch nie eingereicht) länger als die
    konfigurierte Schwelle nichts mehr eingereicht, UND liegt die letzte
    Erinnerung selbst mindestens genauso lange zurück (verhindert
    tägliches Spamming, sobald die Schwelle einmal überschritten ist),
    wird eine Erinnerungsmail verschickt. Gibt die Anzahl verschickter
    Mails zurück.

    Die Ziel-E-Mail ist entweder das explizit gesetzte `Client.email`
    (Coach-Fall: eigene Klienten-Adresse) oder - falls nicht gesetzt - die
    Account-E-Mail des Owners, sofern es ein Single-Account ist (der
    Klient IST hier der User selbst, eine separate "Klienten-E-Mail"
    einzutragen wäre eine unnötige Dopplung, siehe UX-Feedback vom
    2026-08-17). Bei Coach-Accounts ohne explizite Klienten-E-Mail bleibt
    es bewusst bei "keine Erinnerung", die eigene Coach-Adresse wäre hier
    keine sinnvolle Erinnerungsadresse für den Klienten."""
    now = datetime.now(timezone.utc)
    candidates = (
        db.query(Client)
        .filter(Client.checkin_reminder_days.isnot(None))
        .all()
    )

    sent_count = 0
    for client_row in candidates:
        target_email = client_row.email
        if target_email is None:
            owner = client_row.owner
            if owner is not None and owner.account_type == AccountType.SINGLE:
                target_email = owner.email
        if target_email is None:
            continue

        last_submission = (
            db.query(CheckinSubmission)
            .filter(CheckinSubmission.client_id == client_row.id)
            .order_by(CheckinSubmission.submitted_at.desc())
            .first()
        )
        reference_point = last_submission.submitted_at if last_submission else client_row.created_at
        if reference_point.tzinfo is None:
            reference_point = reference_point.replace(tzinfo=timezone.utc)

        days_since_reference = (now - reference_point).days
        if days_since_reference < client_row.checkin_reminder_days:
            continue

        if client_row.last_reminder_sent_at is not None:
            last_reminder = client_row.last_reminder_sent_at
            if last_reminder.tzinfo is None:
                last_reminder = last_reminder.replace(tzinfo=timezone.utc)
            days_since_last_reminder = (now - last_reminder).days
            if days_since_last_reminder < client_row.checkin_reminder_days:
                continue

        checkin_url = f"{settings.frontend_base_url}/checkin/{client_row.checkin_token}"
        send_checkin_reminder_email(to=target_email, checkin_url=checkin_url)
        client_row.last_reminder_sent_at = now
        sent_count += 1

    db.commit()
    return sent_count
