"""
EmailToken = ein einmal verwendbarer, zeitlich befristeter Nachweis für
einen per Mail verschickten Link (E-Mail-Bestätigung oder Passwort-Reset)
- siehe Design-Spec Abschnitt "Datenmodell". Der Link selbst ist ein
signierter itsdangerous-Token (wie Session-Cookies); hier landet nur der
GEHASHTE Token, damit ein DB-Leak keine gültigen Links preisgibt.
"""
import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class EmailTokenPurpose(str, enum.Enum):
    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"
    CHANGE_EMAIL = "change_email"


class EmailToken(Base):
    __tablename__ = "email_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Nur für purpose=CHANGE_EMAIL gesetzt - trägt die angefragte neue
    # Adresse, bis der Bestätigungslink geklickt wird (siehe
    # routers/auth.py change_email/confirm_email_change). Für alle
    # anderen Purposes bleibt das Feld NULL.
    new_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    purpose: Mapped[EmailTokenPurpose] = mapped_column(Enum(EmailTokenPurpose), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="email_tokens")  # noqa: F821

    def __repr__(self) -> str:
        return f"<EmailToken id={self.id} user_id={self.user_id} purpose={self.purpose}>"
