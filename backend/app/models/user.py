"""
User = ein Account, der sich einloggt. Kann `single` (nur eigener
Fortschritt, kein Dashboard) oder `coach` (mehrere Kunden, Dashboard)
sein - siehe Design-Spec Abschnitt "Kontotyp". Jeder User bekommt bei
Anlage automatisch genau einen Client (siehe app/models/client.py),
unabhängig vom account_type.
"""
import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AccountType(str, enum.Enum):
    SINGLE = "single"
    COACH = "coach"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_type: Mapped[AccountType] = mapped_column(
        Enum(AccountType), default=AccountType.SINGLE, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    clients: Mapped[list["Client"]] = relationship(  # noqa: F821
        back_populates="owner", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} account_type={self.account_type}>"
