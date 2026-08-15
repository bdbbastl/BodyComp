"""
Client = das Athleten-Profil (bisher: "die App", jetzt eine von mehreren
verwaltbaren Personen unter einem Account). Jede Pose/jeder DayLog/jedes
Photo hängt an genau einem Client. Jeder User (single oder coach) hat
mindestens einen Client - siehe Design-Spec Abschnitt "Kontotyp".
"""
import secrets
from datetime import date as date_, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    birth_date: Mapped[date_ | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(50), nullable=True)
    start_date: Mapped[date_ | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    # Magic-Link-Zugang für Klienten-Check-in-Einreichung (kein Login, kein
    # Ablauf) - siehe Design-Spec Abschnitt "Magic-Link-Mechanismus". Der
    # Coach kann den Token im Klientenprofil jederzeit neu generieren, was
    # den alten Link sofort ungültig macht.
    checkin_token: Mapped[str] = mapped_column(
        String(64), default=lambda: secrets.token_urlsafe(24), nullable=False
    )
    # Rein intern, NIE im Klienten-Flow sichtbar - siehe Design-Spec.
    coach_private_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Voraussetzung für Erinnerungsmails (siehe services/checkin_reminders.py).
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # None = keine automatische Erinnerung für diesen Klienten.
    checkin_reminder_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    owner: Mapped["User"] = relationship(back_populates="clients")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Client id={self.id} name={self.name!r} owner_id={self.owner_id}>"
