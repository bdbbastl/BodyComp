"""
AppSetting = simples Key-Value-Store für Account-Einstellungen (Gemini-
API-Key, Anzeige-Präferenzen). Hängt an owner_id (User) statt global -
siehe Design-Spec Abschnitt "AppSetting wandert zum Account". Der
Primärschlüssel ist jetzt das Paar (owner_id, key) statt nur key, damit
zwei Accounts denselben Settings-Key (z.B. "gemini_api_key") unabhängig
voneinander belegen können.
"""
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AppSetting(Base):
    __tablename__ = "app_settings"

    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str | None] = mapped_column(String(2000), nullable=True)
