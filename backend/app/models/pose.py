"""
Pose = eine frei konfigurierbare Körperhaltung/-perspektive
(z.B. "Front Double Biceps", "Side Chest", "Rear Lat Spread"), gehört zu
GENAU EINEM Client - jeder Kunde hat seine eigene, unabhängige Pose-Liste
(siehe Design-Spec Abschnitt "Datenmodell").

Start: 7 Standard-Posen pro neuem Client (siehe app/core/seed.py),
erweiterbar bis ~20 über die Einstellungsseite (Pose-CRUD-Router).
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Pose(Base):
    __tablename__ = "poses"
    __table_args__ = (UniqueConstraint("client_id", "name", name="uq_pose_client_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # nullable auf ORM-Ebene (statt nullable=False), obwohl fachlich jede
    # Pose zu genau einem Client gehört: bestehende Datenbestände von vor
    # der Mandantenfähigkeit haben hier NULL, bis das einmalige
    # Migrationsscript (core/migrate_to_multitenancy.py) sie befüllt -
    # siehe Kommentar dort und in core/migrations.py. Anwendungscode setzt
    # client_id beim Anlegen neuer Poses immer explizit (siehe
    # routers/poses.py).
    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Steuert die Reihenfolge in Dropdowns/Grids; frei per Drag&Drop
    # änderbar (POC: einfach hochzählen bei Anlage).
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    photos: Mapped[list["Photo"]] = relationship(  # noqa: F821
        back_populates="pose"
    )

    def __repr__(self) -> str:
        return f"<Pose id={self.id} client_id={self.client_id} name={self.name!r}>"
