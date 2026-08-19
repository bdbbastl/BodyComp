"""
Coach-seitige Review-Ansicht der Check-in-Einreichungen eines Klienten -
siehe Design-Spec Abschnitt "Coach-Ansicht". Nutzt dieselbe
`get_owned_client`-Dependency wie alle anderen client-gescopten Router,
damit ein Coach nie auf fremde Klienten zugreifen kann.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.checkin_submission import CheckinStatus, CheckinSubmission
from app.models.client import Client
from app.models.photo import Photo
from app.routers.clients import get_owned_client
from app.routers.photos import _delete_photo_files
from app.schemas.checkin import CheckinFeedbackUpdate, CheckinSubmissionOut

router = APIRouter(prefix="/api/clients/{client_id}/checkins", tags=["checkins"])


@router.get("", response_model=list[CheckinSubmissionOut])
def list_checkins(client_row: Client = Depends(get_owned_client), db: Session = Depends(get_db)):
    submissions = (
        db.query(CheckinSubmission).filter(CheckinSubmission.client_id == client_row.id).all()
    )
    # Offene zuerst (neueste zuerst innerhalb der jeweiligen Gruppe) -
    # Python-seitig sortiert, da eine SQL-ORDER-BY-Klausel über einen
    # String-Enum-Vergleich fragil gegenüber künftigen Statuswerten wäre.
    submissions.sort(
        key=lambda s: (s.status != CheckinStatus.PENDING, -(s.submitted_at.timestamp()))
    )
    return submissions


@router.patch("/{checkin_id}", response_model=CheckinSubmissionOut)
def update_checkin(
    checkin_id: int,
    payload: CheckinFeedbackUpdate,
    client_row: Client = Depends(get_owned_client),
    db: Session = Depends(get_db),
):
    submission = (
        db.query(CheckinSubmission)
        .filter(CheckinSubmission.id == checkin_id, CheckinSubmission.client_id == client_row.id)
        .first()
    )
    if submission is None:
        raise HTTPException(404, "Check-in not found")

    if payload.coach_feedback_text is not None:
        submission.coach_feedback_text = payload.coach_feedback_text
    if payload.coach_feedback_video_url is not None:
        submission.coach_feedback_video_url = payload.coach_feedback_video_url
    if payload.mark_reviewed:
        submission.status = CheckinStatus.REVIEWED
        submission.reviewed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(submission)
    return submission


@router.delete("/{checkin_id}", status_code=204)
def delete_checkin(
    checkin_id: int, client_row: Client = Depends(get_owned_client), db: Session = Depends(get_db)
):
    """Löscht einen Check-in samt aller zugehörigen Fotos (Dateien + DB-
    Zeilen) unwiderruflich - siehe Design-Spec "Thumbnail-Prefetch +
    Check-in-Löschen". Der DayLog-Eintrag (Gewicht/Notizen) bleibt
    bestehen - Gewicht ist ein Tages-, kein Check-in-Attribut, konsistent
    mit delete_photo() in photos.py."""
    submission = (
        db.query(CheckinSubmission)
        .filter(CheckinSubmission.id == checkin_id, CheckinSubmission.client_id == client_row.id)
        .first()
    )
    if submission is None:
        raise HTTPException(404, "Check-in not found")

    photos = db.query(Photo).filter(Photo.checkin_submission_id == checkin_id).all()
    for photo in photos:
        _delete_photo_files(photo)
        db.delete(photo)
    db.delete(submission)
    db.commit()
