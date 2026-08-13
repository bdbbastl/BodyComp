"""
Account-Einstellungen: Gemini-API-Key und Anzeige-Präferenzen, beide
gebunden an den eingeloggten Account (nicht mehr global, nicht pro
Kunde) - siehe Design-Spec Abschnitt "AppSetting wandert zum Account".
"""
import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.app_setting import AppSetting
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.settings import DisplaySettings, GeminiKeyIn, GeminiKeyStatus
from app.services.ai_comparison import GEMINI_KEY_SETTING, resolve_gemini_api_key

router = APIRouter(prefix="/api/settings", tags=["settings"])

DISPLAY_SETTINGS_KEY = "display_settings"


@router.get("/gemini-key", response_model=GeminiKeyStatus)
def get_gemini_key_status(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> GeminiKeyStatus:
    key, source = resolve_gemini_api_key(db, current_user.id)
    if not key:
        return GeminiKeyStatus(configured=False)
    return GeminiKeyStatus(configured=True, source=source, last4=key[-4:])


@router.put("/gemini-key", response_model=GeminiKeyStatus)
def set_gemini_key(
    payload: GeminiKeyIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GeminiKeyStatus:
    value = payload.api_key.strip()
    setting = db.get(AppSetting, (current_user.id, GEMINI_KEY_SETTING))
    if setting is None:
        setting = AppSetting(owner_id=current_user.id, key=GEMINI_KEY_SETTING, value=value)
        db.add(setting)
    else:
        setting.value = value
    db.commit()
    return GeminiKeyStatus(configured=True, source="settings", last4=value[-4:])


@router.delete("/gemini-key", status_code=204)
def clear_gemini_key(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    """Löscht den in der DB gespeicherten Key - fällt danach ggf. wieder auf
    GEMINI_API_KEY aus .env zurück, falls dort einer gesetzt ist."""
    setting = db.get(AppSetting, (current_user.id, GEMINI_KEY_SETTING))
    if setting is not None:
        db.delete(setting)
        db.commit()


@router.get("/display", response_model=DisplaySettings)
def get_display_settings(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> DisplaySettings:
    """Anzeige-Präferenzen (siehe DisplaySettings) - als ein JSON-Blob in
    einer einzigen AppSetting-Zeile gespeichert, statt einer Zeile pro
    Feld, weil sich die Menge dieser reinen UI-Präferenzen wahrscheinlich
    noch erweitert."""
    setting = db.get(AppSetting, (current_user.id, DISPLAY_SETTINGS_KEY))
    if not setting or not setting.value:
        return DisplaySettings()
    try:
        return DisplaySettings(**json.loads(setting.value))
    except (json.JSONDecodeError, TypeError):
        return DisplaySettings()


@router.put("/display", response_model=DisplaySettings)
def set_display_settings(
    payload: DisplaySettings,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DisplaySettings:
    # Grenzen serverseitig erzwingen, nicht nur im Frontend-<input min/max>.
    clamped = DisplaySettings(
        timeline_columns_max=max(1, min(10, payload.timeline_columns_max)),
        timeline_weeks_per_page=max(1, min(25, payload.timeline_weeks_per_page)),
    )
    value = json.dumps(clamped.model_dump())
    setting = db.get(AppSetting, (current_user.id, DISPLAY_SETTINGS_KEY))
    if setting is None:
        setting = AppSetting(owner_id=current_user.id, key=DISPLAY_SETTINGS_KEY, value=value)
        db.add(setting)
    else:
        setting.value = value
    db.commit()
    return clamped
