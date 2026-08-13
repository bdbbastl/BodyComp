"""
DayLog = Tagesdaten, die NICHT an ein einzelnes Bild gebunden sind.

Wichtig gemäß Anforderung: Körpergewicht wird pro Datum gespeichert,
nicht pro Bild. Ein Tag kann beliebig viele Fotos (verschiedener Posen)
haben, aber genau einen DayLog-Eintrag.
"""
from datetime import date as date_, datetime, timezone

from sqlalchemy import Date, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DayLog(Base):
    __tablename__ = "day_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Ein Datum darf nur einen DayLog haben -> unique.
    date: Mapped[date_] = mapped_column(Date, unique=True, nullable=False, index=True)

    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    photos: Mapped[list["Photo"]] = relationship(  # noqa: F821
        back_populates="day_log"
    )

    def __repr__(self) -> str:
        return f"<DayLog id={self.id} date={self.date} weight_kg={self.weight_kg}>"
