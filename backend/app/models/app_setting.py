"""
AppSetting = simples Key-Value-Store für App-weite Einstellungen, die kein
eigenes Modell rechtfertigen (aktuell nur der optionale, vom User selbst
eingetragene Gemini-API-Key aus den Settings, siehe routers/settings.py).
Ein DB-Wert hat Vorrang vor GEMINI_API_KEY aus backend/.env, damit auch ohne
.env-Bearbeitung jeder User seinen eigenen Key hinterlegen kann.
"""
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str | None] = mapped_column(String(2000), nullable=True)
