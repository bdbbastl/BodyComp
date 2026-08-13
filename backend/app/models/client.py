"""
Client = das Athleten-Profil (bisher: "die App", jetzt eine von mehreren
verwaltbaren Personen unter einem Account). Jede Pose/jeder DayLog/jedes
Photo hängt an genau einem Client. Jeder User (single oder coach) hat
mindestens einen Client - siehe Design-Spec Abschnitt "Kontotyp".
"""
from datetime import date as date_, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String
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
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(50), nullable=True)
    start_date: Mapped[date_ | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    owner: Mapped["User"] = relationship(back_populates="clients")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Client id={self.id} name={self.name!r} owner_id={self.owner_id}>"
