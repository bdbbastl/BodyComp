"""Tagesdaten (aktuell nur Gewicht) pro Kunde."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.client import Client
from app.models.day_log import DayLog
from app.routers.clients import get_owned_client
from app.schemas.day_log import DayLogOut, DayLogUpsert
from app.services.billing import check_and_consume_free_checkin

router = APIRouter(prefix="/api/clients/{client_id}/day-logs", tags=["day-logs"])


@router.get("", response_model=list[DayLogOut])
def list_day_logs(client_row: Client = Depends(get_owned_client), db: Session = Depends(get_db)):
    return (
        db.query(DayLog)
        .filter(DayLog.client_id == client_row.id)
        .order_by(DayLog.date.desc())
        .all()
    )


@router.put("", response_model=DayLogOut)
def upsert_day_log(
    payload: DayLogUpsert,
    client_row: Client = Depends(get_owned_client),
    db: Session = Depends(get_db),
):
    """Legt den DayLog für ein Datum an oder aktualisiert ihn (Gewicht/Notizen)."""
    day_log = (
        db.query(DayLog)
        .filter(DayLog.client_id == client_row.id, DayLog.date == payload.date)
        .first()
    )
    if day_log is None:
        # Nur ein NEUER Tag zählt als Check-in fürs kostenlose Kontingent
        # (siehe Design-Spec) - reines Aktualisieren eines bestehenden
        # Tages ist beliebig oft kostenlos möglich.
        check_and_consume_free_checkin(client_row.owner, db)
        day_log = DayLog(client_id=client_row.id, date=payload.date)
        db.add(day_log)
    day_log.weight_kg = payload.weight_kg
    day_log.notes = payload.notes
    db.commit()
    db.refresh(day_log)
    return day_log
