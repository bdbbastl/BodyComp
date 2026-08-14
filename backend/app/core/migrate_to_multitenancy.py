"""
Einmaliges Migrationsscript: verschiebt die bestehenden Single-Tenant-
Daten (Poses/DayLogs/Photos ohne client_id) in einen neuen Client "Mein
Profil", der einem neu angelegten Account gehört - siehe Design-Spec
Abschnitt "Migration des bestehenden Datenbestands".

Wird von main.py's lifespan bei JEDEM Start aufgerufen, ist aber ein
No-Op, sobald mindestens ein User existiert (Erkennungsmerkmal laut
Spec) - so kann es gefahrlos öfter aufgerufen werden, ohne Daten
doppelt zu migrieren.

Bewegt zusätzlich die betroffenen Dateien auf der Platte in die neue
client-gescopte Ordnerstruktur (siehe services/storage_paths.py) und
aktualisiert die in der DB gespeicherten Pfade entsprechend.
"""
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.client import Client
from app.models.day_log import DayLog
from app.models.photo import Photo
from app.models.pose import Pose
from app.models.user import AccountType, User
from app.services.account import create_account
from app.services.storage_paths import processed_dir_for_client_date


def _move_file_into_client_folder(rel_path: str | None, client_id: int) -> str | None:
    """Verschiebt eine einzelne Datei (original/preview/thumbnail/
    normalized) in den client-gescopten Ordner, behält den restlichen
    Pfad (Datum, Dateiname) bei. Gibt den neuen relativen Pfad zurück,
    oder den unveränderten Wert, wenn die Datei nicht existiert (defensiv
    - eine fehlende Datei blockiert die Migration nicht)."""
    if not rel_path:
        return rel_path

    source = settings.data_dir / rel_path
    if not source.exists():
        return rel_path

    parts = Path(rel_path).parts  # z.B. ("photos_processed", "2026-01-01", "foo.jpg")
    if parts[0] == "photos_processed" and len(parts) >= 3:
        date_str = parts[1]
        filename = Path(*parts[2:])
        dest_dir = processed_dir_for_client_date(client_id, date_str)
    elif parts[0] == "photos_normalized" and len(parts) >= 3:
        pose_id_str = parts[1]
        filename = Path(*parts[2:])
        dest_dir = settings.photos_normalized_dir / str(client_id) / pose_id_str
    elif parts[0] == "photos_incoming" and len(parts) >= 2:
        filename = Path(*parts[1:])
        dest_dir = settings.photos_incoming_dir / str(client_id)
    else:
        return rel_path  # unbekanntes Layout - unverändert lassen

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    shutil.move(str(source), str(dest))
    return dest.relative_to(settings.data_dir).as_posix()


def migrate_to_multitenancy(
    db: Session, *, email: str, password: str, display_name: str
) -> None:
    if db.query(User).count() > 0:
        return  # schon migriert (oder frische Installation ohne Altdaten)

    user = create_account(
        db, email=email, password=password, display_name=display_name
    )
    # create_account legt bereits EINEN Client namens display_name an
    # (siehe services/account.py) - für die Migration bestehender Daten
    # überschreiben wir dessen Namen auf "Mein Profil", statt einen
    # zweiten Client anzulegen.
    client_row = db.query(Client).filter(Client.owner_id == user.id).first()
    client_row.name = "Mein Profil"

    user.account_type = AccountType.COACH
    db.commit()

    poses = db.query(Pose).filter(Pose.client_id.is_(None)).all()
    for pose in poses:
        pose.client_id = client_row.id

    day_logs = db.query(DayLog).filter(DayLog.client_id.is_(None)).all()
    for day_log in day_logs:
        day_log.client_id = client_row.id

    photos = db.query(Photo).filter(Photo.client_id.is_(None)).all()
    for photo in photos:
        photo.client_id = client_row.id
        photo.original_path = _move_file_into_client_folder(photo.original_path, client_row.id)
        photo.preview_path = _move_file_into_client_folder(photo.preview_path, client_row.id)
        photo.thumbnail_path = _move_file_into_client_folder(photo.thumbnail_path, client_row.id)
        photo.normalized_path = _move_file_into_client_folder(photo.normalized_path, client_row.id)

    db.commit()
