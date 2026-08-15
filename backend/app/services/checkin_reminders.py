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
from app.services.email import send_checkin_reminder_email


def run_checkin_reminders(db: Session) -> int:
    """Prüft jeden Client mit gesetzter `email` UND `checkin_reminder_days`:
    wurde seit der letzten Einreichung (oder seit Account-Erstellung, falls
    noch nie eingereicht) länger als die konfigurierte Schwelle nichts
    mehr eingereicht, UND liegt die letzte Erinnerung selbst mindestens
    genauso lange zurück (verhindert tägliches Spamming, sobald die
    Schwelle einmal überschritten ist), wird eine Erinnerungsmail
    verschickt. Gibt die Anzahl verschickter Mails zurück."""
    now = datetime.now(timezone.utc)
    candidates = (
        db.query(Client)
        .filter(Client.email.isnot(None), Client.checkin_reminder_days.isnot(None))
        .all()
    )

    sent_count = 0
    for client_row in candidates:
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
        send_checkin_reminder_email(to=client_row.email, checkin_url=checkin_url)
        client_row.last_reminder_sent_at = now
        sent_count += 1

    db.commit()
    return sent_count
