"""
Foto-Workflow pro Kunde: Ordner-Sync, Unprocessed-Queue, manuelle
Zuordnung, Timeline-Dashboard-Daten.
"""
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date as date_
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.checkin_submission import CheckinStatus, CheckinSubmission
from app.models.client import Client
from app.models.day_log import DayLog
from app.models.photo import Photo, ProcessingStatus
from app.models.pose import Pose
from app.models.user import User
from app.routers.clients import get_owned_client
from app.schemas.photo import (
    PhotoAssign,
    PhotoBulkAssign,
    PhotoOut,
    PhotoRepose,
    PhotoUnprocessedOut,
)
from app.services.billing import check_and_consume_free_checkin
from app.services.folder_sync import sync_incoming_folder
from app.services.pose_normalization import normalize_photo
from app.services.pose_suggestion import compute_pose_suggestions
from app.services.storage_paths import (
    incoming_dir_for_client,
    normalized_dir_for_client_pose,
    processed_dir_for_client_date,
)
from app.services.storage_sync import delete_remote, ensure_local, push
from app.services.thumbnails import generate_thumbnail, thumbnail_path_for

router = APIRouter(prefix="/api/clients/{client_id}/photos", tags=["photos"])

# Begrenzt gleichzeitige Foto-Verarbeitung (Datei-I/O + MediaPipe-
# Inferenz) - verhindert CPU-Überlastung durch zu viele parallele
# Inferenzen auf dem begrenzten Railway-Container. Siehe Design-Spec
# "Foto-Upload/Speicher-Performance".
PHOTO_PROCESSING_MAX_WORKERS = 4


@router.post("/sync", response_model=list[PhotoOut])
def sync_photos(client_row: Client = Depends(get_owned_client), db: Session = Depends(get_db)):
    """Scannt photos_incoming/<client_id>/ und legt neue Photo-Rows als
    UNPROCESSED an."""
    return sync_incoming_folder(db, client_row.id)


@router.post("/upload", response_model=list[PhotoOut])
def upload_photos(
    files: list[UploadFile],
    client_row: Client = Depends(get_owned_client),
    db: Session = Depends(get_db),
):
    """
    Datei-Upload für die Import-Seite: Der User wählt Dateien von der
    eigenen Festplatte, diese werden nach photos_incoming/<client_id>/
    kopiert und direkt im Anschluss verarbeitet (derselbe Scan wie /sync) -
    der User muss also nicht extra einen Ordner auf dem Server-Rechner
    befüllen und anschließend "Sync" klicken, sondern kann Dateien direkt
    aus dem Browser hochladen.

    Performance: alle Dateien werden zuerst schnell lokal geschrieben
    (reine Disk-I/O, bleibt sequenziell), die R2-Uploads laufen danach
    PARALLEL über einen Thread-Pool - die Antwort wartet auf alle, bevor
    sie zurückkommt (siehe Design-Spec "Foto-Upload/Speicher-Performance").
    """
    incoming_dir = incoming_dir_for_client(client_row.id)
    incoming_dir.mkdir(parents=True, exist_ok=True)
    pending_push_paths: list[str] = []
    for upload in files:
        if not upload.filename:
            continue
        # Nur den Dateinamen übernehmen, keine Pfad-Komponenten - der
        # Client-gelieferte Dateiname könnte sonst z.B. "../../evil.jpg"
        # sein und über incoming_dir hinausschreiben (Path-Traversal).
        safe_name = Path(upload.filename).name
        suffix = Path(safe_name).suffix.lower()
        if suffix not in settings.allowed_extensions:
            continue
        dest = incoming_dir / safe_name
        # Namenskollision (z.B. gleicher Dateiname erneut hochgeladen):
        # Zähler anhängen statt zu überschreiben.
        counter = 1
        while dest.exists():
            dest = incoming_dir / f"{Path(safe_name).stem}_{counter}{suffix}"
            counter += 1
        with dest.open("wb") as f:
            shutil.copyfileobj(upload.file, f)
        pending_push_paths.append(dest.relative_to(settings.data_dir).as_posix())

    if not pending_push_paths:
        raise HTTPException(400, "No valid image files found in upload")

    with ThreadPoolExecutor(max_workers=PHOTO_PROCESSING_MAX_WORKERS) as executor:
        futures = [executor.submit(push, rel_path) for rel_path in pending_push_paths]
        for future in as_completed(futures):
            future.result()

    return sync_incoming_folder(db, client_row.id)


@router.get("/unprocessed", response_model=list[PhotoUnprocessedOut])
def list_unprocessed(client_row: Client = Depends(get_owned_client), db: Session = Depends(get_db)):
    photos = (
        db.query(Photo)
        .filter(Photo.client_id == client_row.id, Photo.status == ProcessingStatus.UNPROCESSED)
        .order_by(Photo.taken_at)
        .all()
    )
    suggestions = compute_pose_suggestions(db, photos)
    result = []
    for photo in photos:
        out = PhotoUnprocessedOut.model_validate(photo)
        out.suggested_pose_id = suggestions.get(photo.id)
        result.append(out)
    return result


@router.get("", response_model=list[PhotoOut])
def list_photos(
    pose_id: int | None = None,
    status: ProcessingStatus | None = None,
    client_row: Client = Depends(get_owned_client),
    db: Session = Depends(get_db),
):
    """Für Timeline-Dashboard und Comparison-Mode (Filter nach Pose).

    Fotos, die zu einem noch nicht 'reviewed' Check-in gehören, werden
    ausgeblendet - siehe Design-Spec "Check-in: Client-Pose-Zuordnung +
    Review-gesteuerte Timeline". Fotos ohne checkin_submission_id (normale
    Coach-Uploads) sind davon unberührt.
    """
    q = (
        db.query(Photo)
        .filter(Photo.client_id == client_row.id)
        .outerjoin(CheckinSubmission, Photo.checkin_submission_id == CheckinSubmission.id)
        .filter(
            (Photo.checkin_submission_id.is_(None))
            | (CheckinSubmission.status == CheckinStatus.REVIEWED)
        )
    )
    if pose_id is not None:
        q = q.filter(Photo.pose_id == pose_id)
    if status is not None:
        q = q.filter(Photo.status == status)
    return q.order_by(Photo.taken_at.desc()).all()


@router.post("/renormalize-all", response_model=list[PhotoOut])
def renormalize_all(client_row: Client = Depends(get_owned_client), db: Session = Depends(get_db)):
    """
    Berechnet die normalisierten Versionen aller bereits zugeordneten Fotos
    neu (z.B. nach einer Verbesserung des Normalisierungs-Algorithmus).
    Originale bleiben unangetastet, nur normalized_path/landmarks_json/status
    werden aktualisiert.
    """
    photos = (
        db.query(Photo)
        .filter(Photo.client_id == client_row.id, Photo.pose_id.isnot(None))
        .all()
    )
    for photo in photos:
        # HEIC-Originale kann OpenCV nicht lesen - dann die JPEG-Vorschau
        # als Quelle für die Normalisierung verwenden (siehe services/heic.py).
        ensure_local(photo.preview_path or photo.original_path)
        src = settings.data_dir / (photo.preview_path or photo.original_path)
        if not src.exists():
            continue
        dest = normalized_dir_for_client_pose(client_row.id, photo.pose_id) / f"{photo.id}.jpg"
        result = normalize_photo(src, dest)
        if result.success and result.normalized_path:
            photo.normalized_path = result.normalized_path.relative_to(settings.data_dir).as_posix()
            push(photo.normalized_path)
            photo.landmarks_json = result.landmarks_json
            photo.status = ProcessingStatus.PROCESSED
        else:
            photo.status = ProcessingStatus.NORMALIZATION_FAILED
    db.commit()
    for p in photos:
        db.refresh(p)
    return photos


@router.post("/backfill-thumbnails")
def backfill_thumbnails(
    force: bool = False,
    client_row: Client = Depends(get_owned_client),
    db: Session = Depends(get_db),
) -> dict:
    """
    Generiert Thumbnails für alle Fotos nach, die noch keins haben (z.B.
    Bestandsfotos von vor der Thumbnail-Einführung). Einmalig auszuführen
    nach dem Update - neue Fotos bekommen ihr Thumbnail automatisch bei
    Sync/Upload bzw. Zuordnung.

    force=true regeneriert ALLE Thumbnails neu, auch bereits vorhandene -
    z.B. nach einem Fix in der Thumbnail-Generierung selbst (etwa der
    fehlenden EXIF-Rotation), wo die alten Dateien einfach falsch sind.
    """
    query = db.query(Photo).filter(Photo.client_id == client_row.id)
    if not force:
        query = query.filter(Photo.thumbnail_path.is_(None))
    photos = query.all()
    generated = 0
    for photo in photos:
        ensure_local(photo.preview_path or photo.original_path)
        source = settings.data_dir / (photo.preview_path or photo.original_path)
        if not source.exists():
            continue
        dest = thumbnail_path_for(source)
        if generate_thumbnail(source, dest):
            photo.thumbnail_path = dest.relative_to(settings.data_dir).as_posix()
            push(photo.thumbnail_path)
            generated += 1
    db.commit()
    return {"total_candidates": len(photos), "generated": generated}


def _get_or_create_day_log(db: Session, client_id: int, day_date, owner: User) -> DayLog:
    """Holt den DayLog für ein Datum oder legt ihn an (inkl. Freikontingent-
    Prüfung für neue Tage). Extrahiert aus der früheren _assign_photo, damit
    sowohl die Einzel- als auch die Bulk-Zuordnung dieselbe Logik nutzen -
    wichtig für Bulk: muss VOR dem Parallel-Dispatch pro Item aufgelöst
    werden, da mehrere Fotos desselben Tages sich sonst beim parallelen
    Anlegen desselben DayLog in die Quere kommen könnten (Race Condition).
    `db.flush()` (nicht nur `db.add`) ist nötig, damit ein direkt
    anschließender Aufruf für ein ANDERES Foto desselben Tages im selben
    Batch den gerade erst angelegten (noch nicht committeten) DayLog per
    Query bereits findet - die Test-Session läuft mit autoflush=False."""
    day_log = (
        db.query(DayLog)
        .filter(DayLog.client_id == client_id, DayLog.date == day_date)
        .first()
    )
    if day_log is None:
        check_and_consume_free_checkin(owner, db)
        day_log = DayLog(client_id=client_id, date=day_date)
        db.add(day_log)
        db.flush()
    return day_log


@dataclass
class _ProcessedPhotoFiles:
    """Ergebnis der reinen Datei-/Bildverarbeitung eines Fotos - enthält
    absichtlich KEINE SQLAlchemy-Objekte (Sessions sind nicht thread-safe),
    nur primitive Werte, damit diese Funktion sicher aus einem
    ThreadPoolExecutor-Worker heraus aufgerufen werden kann."""
    original_path: str
    preview_path: str | None
    thumbnail_path: str | None
    normalization_succeeded: bool
    normalized_path: str | None
    landmarks_json: str | None


def _process_photo_files(
    *,
    client_id: int,
    filename: str,
    original_path: str,
    preview_path: str | None,
    thumbnail_path: str | None,
    day_date_iso: str,
    pose_id: int,
    photo_id: int,
) -> _ProcessedPhotoFiles:
    """Alles außer DB-Schreiben: Datei-Move nach photos_processed/,
    Thumbnail-Erzeugung falls fehlend, MediaPipe-Normalisierung, alle
    R2-Uploads. Nimmt und liefert nur primitive Werte (keine ORM-Objekte) -
    sicher aus einem Thread-Pool-Worker aufrufbar. Siehe Design-Spec
    "Foto-Upload/Speicher-Performance" Abschnitt "/photos/assign-bulk"."""
    dest_dir = processed_dir_for_client_date(client_id, day_date_iso)
    dest_dir.mkdir(parents=True, exist_ok=True)

    result_original_path = original_path
    result_preview_path = preview_path
    result_thumbnail_path = thumbnail_path

    ensure_local(original_path)
    src = settings.data_dir / original_path
    if src.exists():
        dest = dest_dir / f"{photo_id}_{filename}"
        shutil.move(str(src), str(dest))
        result_original_path = dest.relative_to(settings.data_dir).as_posix()
        push(result_original_path)

    if preview_path:
        ensure_local(preview_path)
        preview_src = settings.data_dir / preview_path
        if preview_src.exists():
            preview_dest = dest_dir / preview_src.name
            shutil.move(str(preview_src), str(preview_dest))
            result_preview_path = preview_dest.relative_to(settings.data_dir).as_posix()
            push(result_preview_path)

    if thumbnail_path:
        ensure_local(thumbnail_path)
        thumb_src = settings.data_dir / thumbnail_path
        if thumb_src.exists():
            thumb_dest = dest_dir / thumb_src.name
            shutil.move(str(thumb_src), str(thumb_dest))
            result_thumbnail_path = thumb_dest.relative_to(settings.data_dir).as_posix()
            push(result_thumbnail_path)
    if not result_thumbnail_path:
        thumb_source = settings.data_dir / (result_preview_path or result_original_path)
        thumb_dest = dest_dir / thumbnail_path_for(thumb_source).name
        if generate_thumbnail(thumb_source, thumb_dest):
            result_thumbnail_path = thumb_dest.relative_to(settings.data_dir).as_posix()
            push(result_thumbnail_path)

    # MediaPipe-Normalisierung (best effort - siehe Design-Spec).
    # HEIC-Originale kann OpenCV nicht lesen -> Vorschau als Quelle nutzen.
    ensure_local(result_preview_path or result_original_path)
    normalize_source = settings.data_dir / (result_preview_path or result_original_path)
    normalized_dest = normalized_dir_for_client_pose(client_id, pose_id) / f"{photo_id}.jpg"
    norm_result = normalize_photo(normalize_source, normalized_dest)

    normalized_path = None
    landmarks_json = None
    if norm_result.success and norm_result.normalized_path:
        normalized_path = norm_result.normalized_path.relative_to(settings.data_dir).as_posix()
        push(normalized_path)
        landmarks_json = norm_result.landmarks_json

    return _ProcessedPhotoFiles(
        original_path=result_original_path,
        preview_path=result_preview_path,
        thumbnail_path=result_thumbnail_path,
        normalization_succeeded=norm_result.success and norm_result.normalized_path is not None,
        normalized_path=normalized_path,
        landmarks_json=landmarks_json,
    )


def _apply_processed_result(
    db: Session, photo: Photo, day_log: DayLog, pose: Pose, weight_kg: float | None,
    result: _ProcessedPhotoFiles,
) -> Photo:
    """Überträgt das Ergebnis von _process_photo_files auf die ORM-Objekte
    und committet - läuft IMMER im Hauptthread (Sessions sind nicht
    thread-safe). Siehe Design-Spec."""
    if weight_kg is not None:
        day_log.weight_kg = weight_kg

    photo.original_path = result.original_path
    photo.preview_path = result.preview_path
    photo.thumbnail_path = result.thumbnail_path
    photo.pose_id = pose.id
    photo.day_log_id = day_log.id
    photo.updated_at = datetime.utcnow()

    if result.normalization_succeeded:
        photo.normalized_path = result.normalized_path
        photo.landmarks_json = result.landmarks_json
        photo.status = ProcessingStatus.PROCESSED
    else:
        photo.status = ProcessingStatus.NORMALIZATION_FAILED

    db.commit()
    db.refresh(photo)
    return photo


def _assign_photo(db: Session, photo: Photo, pose: Pose, weight_kg: float | None, owner: User) -> Photo:
    """Ordnet EIN Foto zu (Einzel-Endpunkt /assign) - ruft dieselben
    Bausteine wie die Bulk-Zuordnung auf, aber synchron im Hauptthread
    (ein einzelnes Foto profitiert nicht von Parallelisierung). Siehe
    Design-Spec Abschnitt "Einzel-Zuordnung"."""
    day_date = photo.taken_at.date()
    day_log = _get_or_create_day_log(db, photo.client_id, day_date, owner)

    result = _process_photo_files(
        client_id=photo.client_id,
        filename=photo.filename,
        original_path=photo.original_path,
        preview_path=photo.preview_path,
        thumbnail_path=photo.thumbnail_path,
        day_date_iso=day_date.isoformat(),
        pose_id=pose.id,
        photo_id=photo.id,
    )
    return _apply_processed_result(db, photo, day_log, pose, weight_kg, result)


@router.post("/assign-bulk", response_model=list[PhotoOut])
def assign_photos_bulk(
    payload: PhotoBulkAssign,
    client_row: Client = Depends(get_owned_client),
    db: Session = Depends(get_db),
):
    """
    Ordnet mehrere Fotos auf einmal zu (z.B. "Alle zugeordneten speichern"
    in der Unprocessed-Ansicht). Fotos ohne gewählte Pose werden vom
    Frontend gar nicht erst mitgeschickt und bleiben unverändert in der
    Queue. Einzelne fehlerhafte Einträge (unbekannte Foto-/Pose-ID) werden
    übersprungen, statt die gesamte Aktion abzubrechen.

    Performance: die teure Datei-/MediaPipe-Arbeit pro Foto läuft über
    einen Thread-Pool PARALLEL statt sequenziell (siehe Design-Spec
    "Foto-Upload/Speicher-Performance") - die Antwort wartet trotzdem auf
    ALLE Ergebnisse, bevor sie zurückgegeben wird (kein Hintergrund-
    Mechanismus, keine Inkonsistenz-Fenster). DayLog-Auflösung/-Anlage
    bleibt VOR dem Parallel-Dispatch sequenziell, um Race Conditions bei
    mehreren Fotos desselben Tages zu vermeiden.
    """
    # Phase 1 (sequenziell, günstig): validieren + DayLog auflösen.
    work_items = []
    for item in payload.items:
        photo = (
            db.query(Photo)
            .filter(Photo.id == item.photo_id, Photo.client_id == client_row.id)
            .first()
        )
        pose = (
            db.query(Pose)
            .filter(Pose.id == item.pose_id, Pose.client_id == client_row.id)
            .first()
        )
        if not photo or not pose or photo.status != ProcessingStatus.UNPROCESSED:
            continue
        day_date = photo.taken_at.date()
        day_log = _get_or_create_day_log(db, client_row.id, day_date, client_row.owner)
        work_items.append((photo, pose, day_log, item.weight_kg))

    if not work_items:
        return []

    # Phase 2 (parallel, teuer): Datei-Verarbeitung + MediaPipe je Foto.
    with ThreadPoolExecutor(max_workers=PHOTO_PROCESSING_MAX_WORKERS) as executor:
        future_to_index = {
            executor.submit(
                _process_photo_files,
                client_id=client_row.id,
                filename=photo.filename,
                original_path=photo.original_path,
                preview_path=photo.preview_path,
                thumbnail_path=photo.thumbnail_path,
                day_date_iso=day_log.date.isoformat(),
                pose_id=pose.id,
                photo_id=photo.id,
            ): index
            for index, (photo, pose, day_log, weight_kg) in enumerate(work_items)
        }
        results_by_index: dict[int, _ProcessedPhotoFiles] = {}
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            results_by_index[index] = future.result()

    # Phase 3 (sequenziell, günstig): Ergebnisse in DB übernehmen.
    results: list[Photo] = []
    for index, (photo, pose, day_log, weight_kg) in enumerate(work_items):
        results.append(
            _apply_processed_result(db, photo, day_log, pose, weight_kg, results_by_index[index])
        )
    return results


@router.post("/{photo_id}/assign", response_model=PhotoOut)
def assign_photo(
    photo_id: int,
    payload: PhotoAssign,
    client_row: Client = Depends(get_owned_client),
    db: Session = Depends(get_db),
):
    photo = db.query(Photo).filter(Photo.id == photo_id, Photo.client_id == client_row.id).first()
    if not photo:
        raise HTTPException(404, "Photo not found")

    pose = db.query(Pose).filter(Pose.id == payload.pose_id, Pose.client_id == client_row.id).first()
    if not pose:
        raise HTTPException(404, "Pose not found")

    return _assign_photo(db, photo, pose, payload.weight_kg, client_row.owner)


def _delete_photo_files(photo: Photo) -> None:
    """Entfernt alle mit dem Foto verknüpften Dateien von der Platte
    (Original, HEIC-Vorschau, normalisierte Version). Fehlende Dateien
    werden stillschweigend übersprungen (z.B. bei inkonsistentem Zustand)."""
    for rel_path in (photo.original_path, photo.preview_path, photo.normalized_path, photo.thumbnail_path):
        if not rel_path:
            continue
        ensure_local(rel_path)
        file = settings.data_dir / rel_path
        if file.exists():
            file.unlink()
        delete_remote(rel_path)


@router.delete("/by-date/{date}", status_code=200)
def delete_photos_by_date(
    date: date_, client_row: Client = Depends(get_owned_client), db: Session = Depends(get_db)
):
    """
    Löscht alle Fotos eines Kalendertags auf einmal (z.B. "Tag löschen" in
    der Timeline). Der DayLog-Eintrag (Gewicht) bleibt bestehen - der Tag
    verschwindet danach einfach aus der Timeline, da diese nur Tage mit
    Fotos anzeigt.

    Muss VOR der Route "/{photo_id}" registriert sein: FastAPI matcht
    Pfad-Segmente ohne expliziten Typ-Konverter im Pfad-String rein
    string-basiert und validiert den Typ erst danach über die Handler-
    Signatur - "/by-date/2026-01-01" würde sonst fälschlich zuerst gegen
    "/{photo_id}" (photo_id: int) geprüft und mit 422 abgewiesen, statt bei
    einem Nicht-Match einfach zur nächsten Route weiterzugehen.
    """
    photos = (
        db.query(Photo)
        .filter(Photo.client_id == client_row.id)
        .filter(Photo.taken_at >= date)
        .filter(Photo.taken_at < date.fromordinal(date.toordinal() + 1))
        .all()
    )
    for photo in photos:
        _delete_photo_files(photo)
        db.delete(photo)
    db.commit()
    return {"deleted": len(photos)}


@router.delete("/{photo_id}", status_code=204)
def delete_photo(
    photo_id: int, client_row: Client = Depends(get_owned_client), db: Session = Depends(get_db)
):
    """
    Löscht ein Foto (egal ob noch unverarbeitet oder bereits einer Pose
    zugeordnet) inkl. aller zugehörigen Dateien von der Platte. Der
    zugehörige DayLog (Gewicht) bleibt erhalten, auch wenn dadurch keine
    Fotos mehr für diesen Tag existieren - das Gewicht ist eine eigene
    Angabe, kein Foto-Metadatum.
    """
    photo = db.query(Photo).filter(Photo.id == photo_id, Photo.client_id == client_row.id).first()
    if not photo:
        raise HTTPException(404, "Photo not found")

    _delete_photo_files(photo)
    db.delete(photo)
    db.commit()


@router.patch("/{photo_id}/pose", response_model=PhotoOut)
def change_photo_pose(
    photo_id: int,
    payload: PhotoRepose,
    client_row: Client = Depends(get_owned_client),
    db: Session = Depends(get_db),
):
    """
    Ordnet ein bereits zugeordnetes Foto nachträglich einer anderen Pose
    zu (z.B. Fehlzuordnung in der Timeline korrigieren). Normalisierte
    Version wird für die neue Pose neu berechnet, die alte Datei am alten
    Pose-Pfad wird aufgeräumt.
    """
    photo = db.query(Photo).filter(Photo.id == photo_id, Photo.client_id == client_row.id).first()
    if not photo:
        raise HTTPException(404, "Photo not found")

    pose = db.query(Pose).filter(Pose.id == payload.pose_id, Pose.client_id == client_row.id).first()
    if not pose:
        raise HTTPException(404, "Pose not found")

    if photo.pose_id == pose.id:
        return photo

    if photo.normalized_path:
        ensure_local(photo.normalized_path)
    old_normalized = settings.data_dir / photo.normalized_path if photo.normalized_path else None
    old_normalized_rel_path = photo.normalized_path

    photo.pose_id = pose.id
    photo.updated_at = datetime.utcnow()

    ensure_local(photo.preview_path or photo.original_path)
    normalize_source = settings.data_dir / (photo.preview_path or photo.original_path)
    normalized_dest = normalized_dir_for_client_pose(client_row.id, pose.id) / f"{photo.id}.jpg"
    result = normalize_photo(normalize_source, normalized_dest)
    if result.success and result.normalized_path:
        photo.normalized_path = result.normalized_path.relative_to(settings.data_dir).as_posix()
        push(photo.normalized_path)
        photo.landmarks_json = result.landmarks_json
        photo.status = ProcessingStatus.PROCESSED
    else:
        photo.normalized_path = None
        photo.status = ProcessingStatus.NORMALIZATION_FAILED

    db.commit()
    db.refresh(photo)

    if old_normalized and old_normalized.exists():
        old_normalized.unlink()
    if old_normalized_rel_path:
        delete_remote(old_normalized_rel_path)

    return photo
