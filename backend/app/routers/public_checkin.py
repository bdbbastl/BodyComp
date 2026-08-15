"""
Öffentlicher, passwortloser Zugang für Klienten: Check-in einreichen und
eigene Historie/Coach-Feedback einsehen - siehe Design-Spec Abschnitt
"Magic-Link-Mechanismus". Auth läuft NICHT über das Session-Cookie,
sondern über den opaken `Client.checkin_token` in der URL.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.client import Client
from app.models.checkin_submission import CheckinSubmission
from app.schemas.checkin import PublicCheckinPageOut

router = APIRouter(prefix="/api/public/checkin", tags=["public-checkin"])


def get_client_by_checkin_token(token: str, db: Session = Depends(get_db)) -> Client:
    """Analog zu `get_owned_client` in routers/clients.py, aber für den
    öffentlichen Zugang: lädt den Client NUR über den Magic-Link-Token,
    keine Session nötig. 404 bei unbekanntem/regeneriertem Token."""
    client_row = db.query(Client).filter(Client.checkin_token == token).first()
    if client_row is None:
        raise HTTPException(404, "Link ungültig")
    return client_row


@router.get("/{token}", response_model=PublicCheckinPageOut)
def get_checkin_page(
    client_row: Client = Depends(get_client_by_checkin_token), db: Session = Depends(get_db)
):
    submissions = (
        db.query(CheckinSubmission)
        .filter(CheckinSubmission.client_id == client_row.id)
        .order_by(CheckinSubmission.submitted_at.desc())
        .all()
    )
    return PublicCheckinPageOut(client_name=client_row.name, submissions=submissions)
