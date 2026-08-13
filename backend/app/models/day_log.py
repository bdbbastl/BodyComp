"""
DayLog = Tagesdaten, die NICHT an ein einzelnes Bild gebunden sind, gehört
zu GENAU EINEM Client.

Wichtig gemäß Anforderung: Körpergewicht wird pro Datum UND Client
gespeichert, nicht pro Bild. Ein Tag kann pro Client beliebig viele Fotos
(verschiedener Posen) haben, aber genau einen DayLog-Eintrag.
"""
from datetime import date as date_, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DayLog(Base):
    __tablename__ = "day_logs"
    __table_args__ = (UniqueConstraint("client_id", "date", name="uq_daylog_client_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )

    date: Mapped[date_] = mapped_column(Date, nullable=False, index=True)

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
        return f"<DayLog id={self.id} client_id={self.client_id} date={self.date} weight_kg={self.weight_kg}>"
