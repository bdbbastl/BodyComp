"""
Zentrale Pfad-Konstruktion für client-gescopte Dateiablage - siehe
Design-Spec Abschnitt "Dateiablage". Jede Datei-Operation in
routers/photos.py und services/folder_sync.py geht durch diese
Funktionen, statt Pfade selbst zusammenzubauen - das ist die zentrale
Stelle, die bei einem späteren Umstieg auf Object-Storage (Stufe 3)
ausgetauscht werden müsste.
"""
from pathlib import Path

from app.core.config import settings


def incoming_dir_for_client(client_id: int) -> Path:
    return settings.photos_incoming_dir / str(client_id)


def processed_dir_for_client_date(client_id: int, date_str: str) -> Path:
    return settings.photos_processed_dir / str(client_id) / date_str


def normalized_dir_for_client_pose(client_id: int, pose_id: int) -> Path:
    return settings.photos_normalized_dir / str(client_id) / str(pose_id)
