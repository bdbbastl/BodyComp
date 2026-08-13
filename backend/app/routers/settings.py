"""
App-Einstellungen, aktuell nur der optionale Gemini-API-Key: der User kann
seinen eigenen kostenlosen Key direkt in der UI hinterlegen, statt
backend/.env von Hand zu editieren. Ein in der DB gespeicherter Key hat
Vorrang vor GEMINI_API_KEY aus .env (siehe services/ai_comparison.py
-> resolve_gemini_api_key).
"""
import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.settings import DisplaySettings, GeminiKeyIn, GeminiKeyStatus
from app.services.ai_comparison import GEMINI_KEY_SETTING, resolve_gemini_api_key
from app.models.app_setting import AppSetting

router = APIRouter(prefix="/api/settings", tags=["settings"])

DISPLAY_SETTINGS_KEY = "display_settings"


@router.get("/gemini-key", response_model=GeminiKeyStatus)
def get_gemini_key_status(db: Session = Depends(get_db)) -> GeminiKeyStatus:
    key, source = resolve_gemini_api_key(db)
    if not key:
        return GeminiKeyStatus(configured=False)
    return GeminiKeyStatus(configured=True, source=source, last4=key[-4:])


@router.put("/gemini-key", response_model=GeminiKeyStatus)
def set_gemini_key(payload: GeminiKeyIn, db: Session = Depends(get_db)) -> GeminiKeyStatus:
    value = payload.api_key.strip()
    setting = db.get(AppSetting, GEMINI_KEY_SETTING)
    if setting is None:
        setting = AppSetting(key=GEMINI_KEY_SETTING, value=value)
        db.add(setting)
    else:
        setting.value = value
    db.commit()
    return GeminiKeyStatus(configured=True, source="settings", last4=value[-4:])


@router.delete("/gemini-key", status_code=204)
def clear_gemini_key(db: Session = Depends(get_db)) -> None:
    """Löscht den in der DB gespeicherten Key - fällt danach ggf. wieder auf
    GEMINI_API_KEY aus .env zurück, falls dort einer gesetzt ist."""
    setting = db.get(AppSetting, GEMINI_KEY_SETTING)
    if setting is not None:
        db.delete(setting)
        db.commit()


@router.get("/display", response_model=DisplaySettings)
def get_display_settings(db: Session = Depends(get_db)) -> DisplaySettings:
    """Anzeige-Präferenzen (siehe DisplaySettings) - als ein JSON-Blob in
    einer einzigen AppSetting-Zeile gespeichert, statt einer Zeile pro
    Feld, weil sich die Menge dieser reinen UI-Präferenzen wahrscheinlich
    noch erweitert."""
    setting = db.get(AppSetting, DISPLAY_SETTINGS_KEY)
    if not setting or not setting.value:
        return DisplaySettings()
    try:
        return DisplaySettings(**json.loads(setting.value))
    except (json.JSONDecodeError, TypeError):
        return DisplaySettings()


@router.put("/display", response_model=DisplaySettings)
def set_display_settings(payload: DisplaySettings, db: Session = Depends(get_db)) -> DisplaySettings:
    # Grenzen serverseitig erzwingen, nicht nur im Frontend-<input min/max>.
    clamped = DisplaySettings(
        timeline_columns_max=max(1, min(10, payload.timeline_columns_max)),
        timeline_weeks_per_page=max(1, min(25, payload.timeline_weeks_per_page)),
    )
    value = json.dumps(clamped.model_dump())
    setting = db.get(AppSetting, DISPLAY_SETTINGS_KEY)
    if setting is None:
        setting = AppSetting(key=DISPLAY_SETTINGS_KEY, value=value)
        db.add(setting)
    else:
        setting.value = value
    db.commit()
    return clamped
