"""
CheckinSubmission = eine vom Klienten über den Magic-Link (siehe
routers/public_checkin.py) eingereichte Check-in-Meldung. Schlanke
"Posteingang"-Schicht oberhalb von DayLog/Photo (siehe Design-Spec
Abschnitt "Architektur-Entscheidung") - schreibt zusätzlich ganz normal
in DayLog/Photo, ist selbst aber der Anker für Review-Status und
Coach-Feedback.
"""
import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CheckinStatus(str, enum.Enum):
    PENDING = "pending"
    REVIEWED = "reviewed"


class CheckinSubmission(Base):
    __tablename__ = "checkin_submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    client_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[CheckinStatus] = mapped_column(
        Enum(CheckinStatus), default=CheckinStatus.PENDING, nullable=False, index=True
    )
    coach_feedback_text: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    coach_feedback_video_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    photos: Mapped[list["Photo"]] = relationship(  # noqa: F821
        back_populates="checkin_submission"
    )

    def __repr__(self) -> str:
        return f"<CheckinSubmission id={self.id} client_id={self.client_id} status={self.status}>"
