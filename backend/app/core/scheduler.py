"""
Täglicher Hintergrund-Job für Check-in-Erinnerungen - siehe Design-Spec
Abschnitt "Benachrichtigungen". In-Process (APScheduler BackgroundScheduler,
läuft in einem eigenen Thread) statt externem Cron, weil die App aktuell
als Single-Process-Deployment läuft (siehe core/rate_limit.py für dieselbe
Design-Entscheidung an anderer Stelle) - für Stufe 3 (Mehrserver-Hosting)
müsste das auf einen verteilten Scheduler wechseln.
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)


def _run_reminders_job() -> None:
    # Lazy-Import von main, damit zur Laufzeit (nicht beim Modul-Import)
    # aufgelöst wird, welche SessionLocal aktuell gilt - wichtig, weil
    # tests/conftest.py `app.main.SessionLocal` pro Test durch eine
    # frische Test-DB-Session-Factory ersetzt (siehe dortige Doku).
    import app.main as main_module
    from app.services.checkin_reminders import run_checkin_reminders

    db = main_module.SessionLocal()
    try:
        sent = run_checkin_reminders(db)
        if sent:
            logger.info("Check-in-Erinnerungen verschickt: %d", sent)
    except Exception:
        logger.exception("Check-in-Erinnerungs-Job fehlgeschlagen")
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(_run_reminders_job, "cron", hour=9, minute=0, id="checkin_reminders")
    scheduler.start()
    return scheduler
