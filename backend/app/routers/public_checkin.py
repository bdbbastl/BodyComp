"""
Öffentlicher, passwortloser Zugang für Klienten: Check-in einreichen und
eigene Historie/Coach-Feedback einsehen - siehe Design-Spec Abschnitt
"Magic-Link-Mechanismus". Auth läuft NICHT über das Session-Cookie,
sondern über den opaken `Client.checkin_token` in der URL.
"""
import logging
import shutil
from datetime import date as date_
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import RateLimiter
from app.models.client import Client
from app.models.checkin_submission import CheckinSubmission
from app.models.day_log import DayLog
from app.schemas.checkin import CheckinSubmissionOut, PublicCheckinPageOut
from app.services.billing import check_and_consume_free_checkin
from app.services.email import send_checkin_submitted_email
from app.services.folder_sync import sync_incoming_folder
from app.services.storage_paths import incoming_dir_for_client
from app.services.storage_sync import push

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/public/checkin", tags=["public-checkin"])

# Großzügig genug für normale Nutzung (mehrmals täglich in Contest Prep
# denkbar, siehe Design-Spec), verhindert aber Missbrauch des
# unauthentifizierten Endpunkts.
checkin_submit_rate_limit = RateLimiter(max_requests=30, window_seconds=3600)

# Grobe Obergrenzen gegen Disk-Fill-Missbrauch - dieser Endpunkt ist
# unauthentifiziert, die 30/h-Rate-Limit-Grenze allein begrenzt die
# Datenmenge pro Stunde noch nicht ausreichend (30 Requests x viele große
# Dateien). Handy-Fotos einer Check-in-Session liegen weit darunter.
MAX_FILES_PER_SUBMISSION = 10
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024


def get_client_by_checkin_token(token: str, db: Session = Depends(get_db)) -> Client:
    """Analog zu `get_owned_client` in routers/clients.py, aber für den
    öffentlichen Zugang: lädt den Client NUR über den Magic-Link-Token,
    keine Session nötig. 404 bei unbekanntem/regeneriertem Token."""
    client_row = db.query(Client).filter(Client.checkin_token == token).first()
    if client_row is None:
        raise HTTPException(404, "Link is invalid")
    return client_row


@router.get("/{token}", response_model=PublicCheckinPageOut)
def get_checkin_page(
    client_row: Client = Depends(get_client_by_checkin_token), db: Session = Depends(get_db)
):
    submissions = (
        db.query(CheckinSubmission)
        .filter(CheckinSubmission.client_id == client_row.id)
        .order_by(CheckinSubmission.submitted_at.desc())
        .all()
    )
    return PublicCheckinPageOut(client_name=client_row.name, submissions=submissions)


@router.post("/{token}/submit", response_model=CheckinSubmissionOut, status_code=201)
def submit_checkin(
    weight_kg: float | None = Form(default=None),
    client_note: str | None = Form(default=None),
    files: list[UploadFile] = File(default=[]),
    client_row: Client = Depends(get_client_by_checkin_token),
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(checkin_submit_rate_limit),
):
    # Vor jeder DB-Schreibung validieren, damit eine abgelehnte Einreichung
    # niemals einen halb gespeicherten Zustand hinterlässt (Submission/
    # DayLog ohne die dazugehörigen Fotos).
    if len(files) > MAX_FILES_PER_SUBMISSION:
        raise HTTPException(400, f"Maximum {MAX_FILES_PER_SUBMISSION} photos per check-in")
    for upload in files:
        if upload.size is not None and upload.size > MAX_FILE_SIZE_BYTES:
            raise HTTPException(400, "File too large (max. 25 MB per photo)")

    submission = CheckinSubmission(
        client_id=client_row.id, weight_kg=weight_kg, client_note=client_note
    )
    db.add(submission)
    db.flush()

    # Gewicht/Notiz landen im DayLog des HEUTIGEN Datums (der Klient
    # berichtet "heute geht es mir so", unabhängig vom EXIF-Datum
    # eventuell mitgeschickter Fotos - die werden unten separat und
    # unverändert nach ihrem eigenen Aufnahmedatum einsortiert).
    if weight_kg is not None or client_note:
        today = date_.today()
        day_log = (
            db.query(DayLog)
            .filter(DayLog.client_id == client_row.id, DayLog.date == today)
            .first()
        )
        if day_log is None:
            # Auch der Magic-Link-Check-in muss das kostenlose
            # Kontingent von Single-Accounts zählen - sonst wäre dieser
            # Endpunkt eine Umgehung der Paywall in day_logs.py/photos.py
            # (gefunden im finalen Billing-Review).
            check_and_consume_free_checkin(client_row.owner, db)
            day_log = DayLog(client_id=client_row.id, date=today)
            db.add(day_log)
        if weight_kg is not None:
            day_log.weight_kg = weight_kg
        if client_note:
            day_log.notes = client_note

    db.commit()

    # Fotos wie beim normalen Upload (routers/photos.py upload_photos)
    # nach photos_incoming/<client_id>/ kopieren und dieselbe
    # Sync-Pipeline nutzen (EXIF/HEIC/Thumbnail-Handling) - dann die neu
    # entstandenen Photo-Rows dieser Einreichung zuordnen. Pose-Zuordnung
    # bleibt bewusst Coach-Aufgabe im bestehenden Import-Screen.
    if files:
        incoming_dir = incoming_dir_for_client(client_row.id)
        incoming_dir.mkdir(parents=True, exist_ok=True)
        # Sammelt die tatsächlich in DIESEM Request geschriebenen Pfade -
        # `sync_incoming_folder` scannt den GESAMTEN incoming_dir (auch
        # Dateien, die der Coach manuell dorthin kopiert und noch nicht
        # synchronisiert hat, siehe folder_sync.py). Ohne diese Liste
        # würden solche fremden, älteren Dateien fälschlich dieser
        # Einreichung zugeordnet (gefunden im finalen Review).
        written_paths: set[str] = set()
        for upload in files:
            if not upload.filename:
                continue
            # Nur den Dateinamen übernehmen, keine Pfad-Komponenten - dieser
            # Endpunkt ist unauthentifiziert, ein manipulierter Dateiname
            # wie "../../evil.jpg" dürfte niemals außerhalb von
            # incoming_dir schreiben können (Path-Traversal).
            safe_name = Path(upload.filename).name
            suffix = Path(safe_name).suffix.lower()
            if suffix not in settings.allowed_extensions:
                continue
            dest = incoming_dir / safe_name
            counter = 1
            while dest.exists():
                dest = incoming_dir / f"{Path(safe_name).stem}_{counter}{suffix}"
                counter += 1
            with dest.open("wb") as f:
                shutil.copyfileobj(upload.file, f)
            written_paths.add(dest.relative_to(settings.data_dir).as_posix())
            push(dest.relative_to(settings.data_dir).as_posix())

        new_photos = sync_incoming_folder(db, client_row.id)
        for photo in new_photos:
            if photo.original_path in written_paths:
                photo.checkin_submission_id = submission.id
        db.commit()

    db.refresh(submission)

    # Coach-Benachrichtigung - best effort, ein Mail-Fehler soll die
    # erfolgreich gespeicherte Einreichung nicht rückgängig machen.
    try:
        checkins_url = f"{settings.frontend_base_url}/clients/{client_row.id}/checkins"
        send_checkin_submitted_email(
            to=client_row.owner.email, client_name=client_row.name, checkins_url=checkins_url
        )
    except Exception:
        logger.warning("Konnte Check-in-Benachrichtigung nicht senden", exc_info=True)

    return submission
