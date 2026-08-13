"""Tagesdaten (aktuell nur Gewicht). Wird primär aus dem Assign-Flow und
dem Timeline-Dashboard heraus verwendet."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.day_log import DayLog
from app.schemas.day_log import DayLogOut, DayLogUpsert

router = APIRouter(prefix="/api/day-logs", tags=["day-logs"])


@router.get("", response_model=list[DayLogOut])
def list_day_logs(db: Session = Depends(get_db)):
    return db.query(DayLog).order_by(DayLog.date.desc()).all()


@router.put("", response_model=DayLogOut)
def upsert_day_log(payload: DayLogUpsert, db: Session = Depends(get_db)):
    """Legt den DayLog für ein Datum an oder aktualisiert ihn (Gewicht/Notizen)."""
    day_log = db.query(DayLog).filter(DayLog.date == payload.date).first()
    if day_log is None:
        day_log = DayLog(date=payload.date)
        db.add(day_log)
    day_log.weight_kg = payload.weight_kg
    day_log.notes = payload.notes
    db.commit()
    db.refresh(day_log)
    return day_log
