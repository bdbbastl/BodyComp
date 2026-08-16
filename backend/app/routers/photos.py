"""
Foto-Workflow pro Kunde: Ordner-Sync, Unprocessed-Queue, manuelle
Zuordnung, Timeline-Dashboard-Daten.
"""
import shutil
from datetime import date as date_
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
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
    """
    incoming_dir = incoming_dir_for_client(client_row.id)
    incoming_dir.mkdir(parents=True, exist_ok=True)
    saved_any = False
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
        push(dest.relative_to(settings.data_dir).as_posix())
        saved_any = True

    if not saved_any:
        raise HTTPException(400, "Keine gültigen Bilddateien im Upload gefunden")

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
    """Für Timeline-Dashboard und Comparison-Mode (Filter nach Pose)."""
    q = db.query(Photo).filter(Photo.client_id == client_row.id)
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


def _assign_photo(db: Session, photo: Photo, pose: Pose, weight_kg: float | None, owner: User) -> Photo:
    """
    Ordnet ein Unprocessed-Bild einer Pose zu:
    1. DayLog für das EXIF-Datum holen/anlegen, optional Gewicht setzen.
    2. Datei von photos_incoming/<client_id>/ nach
       photos_processed/<client_id>/<date>/ verschieben.
    3. MediaPipe-Normalisierung anstoßen (best effort - Fehler blockieren
       die Zuordnung nicht, siehe ProcessingStatus.NORMALIZATION_FAILED).
    Von /assign (Einzelfoto) und /assign-bulk (Massenzuordnung) gemeinsam
    genutzt, damit beide exakt dieselbe Logik durchlaufen.
    """
    day_date = photo.taken_at.date()
    day_log = (
        db.query(DayLog)
        .filter(DayLog.client_id == photo.client_id, DayLog.date == day_date)
        .first()
    )
    if day_log is None:
        check_and_consume_free_checkin(owner)
        day_log = DayLog(client_id=photo.client_id, date=day_date)
        db.add(day_log)
        db.flush()
    if weight_kg is not None:
        day_log.weight_kg = weight_kg

    # Datei physisch verschieben: photos_processed/<client_id>/<YYYY-MM-DD>/<filename>
    ensure_local(photo.original_path)
    src = settings.data_dir / photo.original_path
    dest_dir = processed_dir_for_client_date(photo.client_id, day_date.isoformat())
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / photo.filename
    if src.exists():
        shutil.move(str(src), str(dest))
        photo.original_path = dest.relative_to(settings.data_dir).as_posix()
        push(photo.original_path)

    # HEIC-Vorschau (falls vorhanden) zusammen mit dem Original verschieben,
    # damit preview_path danach noch auf eine existierende Datei zeigt.
    if photo.preview_path:
        ensure_local(photo.preview_path)
        preview_src = settings.data_dir / photo.preview_path
        if preview_src.exists():
            preview_dest = dest_dir / preview_src.name
            shutil.move(str(preview_src), str(preview_dest))
            photo.preview_path = preview_dest.relative_to(settings.data_dir).as_posix()
            push(photo.preview_path)

    # Thumbnail ebenso mitverschieben (analog zur HEIC-Vorschau); fehlt es
    # noch (z.B. Foto aus einer Zeit vor Einführung der Thumbnails), wird
    # es hier direkt am neuen Ort nachgeneriert statt verschoben.
    if photo.thumbnail_path:
        ensure_local(photo.thumbnail_path)
        thumb_src = settings.data_dir / photo.thumbnail_path
        if thumb_src.exists():
            thumb_dest = dest_dir / thumb_src.name
            shutil.move(str(thumb_src), str(thumb_dest))
            photo.thumbnail_path = thumb_dest.relative_to(settings.data_dir).as_posix()
            push(photo.thumbnail_path)
    if not photo.thumbnail_path:
        thumb_source = settings.data_dir / (photo.preview_path or photo.original_path)
        thumb_dest = dest_dir / thumbnail_path_for(thumb_source).name
        if generate_thumbnail(thumb_source, thumb_dest):
            photo.thumbnail_path = thumb_dest.relative_to(settings.data_dir).as_posix()
            push(photo.thumbnail_path)

    photo.pose_id = pose.id
    photo.day_log_id = day_log.id
    photo.status = ProcessingStatus.PROCESSED
    photo.updated_at = datetime.utcnow()

    db.commit()

    # MediaPipe-Normalisierung synchron anstoßen (POC-Entscheidung).
    # Fehler blockieren die Zuordnung nicht - Pose/DayLog bleiben gesetzt,
    # nur der Overlay-Vergleich ist für dieses Bild dann nicht verfügbar.
    # HEIC-Originale kann OpenCV nicht lesen -> Vorschau als Quelle nutzen.
    ensure_local(photo.preview_path or photo.original_path)
    normalize_source = settings.data_dir / (photo.preview_path or photo.original_path)
    normalized_dest = normalized_dir_for_client_pose(photo.client_id, pose.id) / f"{photo.id}.jpg"
    result = normalize_photo(normalize_source, normalized_dest)
    if result.success and result.normalized_path:
        photo.normalized_path = result.normalized_path.relative_to(settings.data_dir).as_posix()
        push(photo.normalized_path)
        photo.landmarks_json = result.landmarks_json
    else:
        photo.status = ProcessingStatus.NORMALIZATION_FAILED

    db.commit()
    db.refresh(photo)
    return photo


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
    """
    results: list[Photo] = []
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
        results.append(_assign_photo(db, photo, pose, item.weight_kg, client_row.owner))
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
        raise HTTPException(404, "Foto nicht gefunden")

    pose = db.query(Pose).filter(Pose.id == payload.pose_id, Pose.client_id == client_row.id).first()
    if not pose:
        raise HTTPException(404, "Pose nicht gefunden")

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
        raise HTTPException(404, "Foto nicht gefunden")

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
        raise HTTPException(404, "Foto nicht gefunden")

    pose = db.query(Pose).filter(Pose.id == payload.pose_id, Pose.client_id == client_row.id).first()
    if not pose:
        raise HTTPException(404, "Pose nicht gefunden")

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
