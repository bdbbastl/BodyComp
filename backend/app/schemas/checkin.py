# backend/app/schemas/checkin.py
from datetime import datetime

from pydantic import BaseModel

from app.models.checkin_submission import CheckinStatus
from app.schemas.photo import PhotoOut


class CheckinSubmissionOut(BaseModel):
    id: int
    submitted_at: datetime
    weight_kg: float | None
    client_note: str | None
    status: CheckinStatus
    coach_feedback_text: str | None
    coach_feedback_video_url: str | None
    reviewed_at: datetime | None
    photos: list[PhotoOut]

    class Config:
        from_attributes = True


class CheckinFeedbackUpdate(BaseModel):
    """Payload für die Coach-Antwort auf einen Check-in. Alle Felder
    optional - der Coach kann z.B. nur "als geprüft markieren" klicken,
    ohne Text/Link zu setzen, oder umgekehrt nur Feedback speichern ohne
    schon final abzuschließen."""

    coach_feedback_text: str | None = None
    coach_feedback_video_url: str | None = None
    mark_reviewed: bool = False


class PublicCheckinSubmissionOut(BaseModel):
    """Wie CheckinSubmissionOut, aber für die öffentliche Klienten-Ansicht
    - bewusst dasselbe Shape (Klient soll sein eigenes Feedback sehen),
    eigener Typ nur zur klaren Trennung von der Coach-Route."""

    id: int
    submitted_at: datetime
    weight_kg: float | None
    client_note: str | None
    status: CheckinStatus
    coach_feedback_text: str | None
    coach_feedback_video_url: str | None
    photos: list[PhotoOut]

    class Config:
        from_attributes = True


class PublicCheckinPageOut(BaseModel):
    client_name: str
    submissions: list[PublicCheckinSubmissionOut]
