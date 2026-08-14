"""
User = ein Account, der sich einloggt. Kann `single` (nur eigener
Fortschritt, kein Dashboard) oder `coach` (mehrere Kunden, Dashboard)
sein - siehe Design-Spec Abschnitt "Kontotyp". Jeder User bekommt bei
Anlage automatisch genau einen Client (siehe app/models/client.py),
unabhängig vom account_type.

Stufe 2 (Public Auth): password_hash ist jetzt nullable, da ein
rein über Google registrierter Account kein eigenes Passwort hat.
google_id verknüpft mit Googles OAuth-Konto (`sub`-Claim).
email_verified_at ist NULL, bis die E-Mail bestätigt wurde (Google-
Accounts sind sofort verifiziert). privacy_accepted_at ist der
Zustimmungs-Nachweis zur Datenschutzerklärung (DSGVO).
sessions_invalidated_at wird bei einem Passwort-Reset gesetzt, um
alle vorher ausgestellten Session-Cookies ungültig zu machen.
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
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_type: Mapped[AccountType] = mapped_column(
        Enum(AccountType), default=AccountType.SINGLE, nullable=False
    )
    google_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    privacy_accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sessions_invalidated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    clients: Mapped[list["Client"]] = relationship(  # noqa: F821
        back_populates="owner", cascade="all, delete-orphan"
    )
    email_tokens: Mapped[list["EmailToken"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} account_type={self.account_type}>"
