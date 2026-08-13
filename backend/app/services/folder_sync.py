"""
Ordner-Sync: scannt photos_incoming/ nach neuen Bilddateien, die noch
nicht als Photo-Row in der DB existieren, und legt sie mit
status=UNPROCESSED an.

POC: einfacher Scan-on-Demand (Endpoint POST /api/photos/sync). Eine
spätere Ausbaustufe könnte watchdog.Observer für Live-Filesystem-Events
nutzen (Dependency ist bereits in requirements.txt vorbereitet).
"""
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.photo import Photo, ProcessingStatus
from app.services.exif import get_dimensions, get_taken_at
from app.services.heic import generate_preview, is_heic
from app.services.thumbnails import generate_thumbnail, thumbnail_path_for


def _preview_path_for(original: Path) -> Path:
    """Konvention: Vorschau liegt direkt neben dem Original, gleicher
    Dateiname + .preview.jpg-Suffix - bleibt so beim Verschieben leicht
    zusammen mit dem Original auffindbar."""
    return original.parent / f"{original.name}.preview.jpg"


def _backfill_missing_previews(db: Session) -> None:
    """
    Erzeugt Vorschauen für HEIC-Fotos nach, die vor Einführung der
    HEIC-Unterstützung synchronisiert wurden (preview_path noch NULL).
    Nur für UNPROCESSED Fotos relevant - danach betrifft es
    /photos/{id}/assign, das preview_path beim Verschieben mitführt.
    """
    candidates = (
        db.query(Photo)
        .filter(Photo.status == ProcessingStatus.UNPROCESSED)
        .filter(Photo.preview_path.is_(None))
        .all()
    )
    changed = False
    for photo in candidates:
        file = settings.data_dir / photo.original_path
        if not file.exists() or not is_heic(file):
            continue
        preview_dest = _preview_path_for(file)
        if generate_preview(file, preview_dest):
            photo.preview_path = preview_dest.relative_to(settings.data_dir).as_posix()
            changed = True
            if photo.width is None or photo.height is None:
                try:
                    photo.width, photo.height = get_dimensions(preview_dest)
                except Exception:
                    pass
    if changed:
        db.commit()


def sync_incoming_folder(db: Session) -> list[Photo]:
    _backfill_missing_previews(db)

    existing_paths = {p.original_path for p in db.query(Photo.original_path).all()}
    new_photos: list[Photo] = []

    for file in sorted(settings.photos_incoming_dir.rglob("*")):
        if not file.is_file() or file.suffix.lower() not in settings.allowed_extensions:
            continue
        # Selbst erzeugte HEIC-Vorschaudateien nicht als eigenständiges
        # neues Foto einlesen (liegen im selben Ordner, s. _preview_path_for).
        if file.name.endswith(".preview.jpg"):
            continue

        rel_path = file.relative_to(settings.data_dir).as_posix()
        if rel_path in existing_paths:
            continue

        taken_at = get_taken_at(file)

        preview_rel_path: str | None = None
        if is_heic(file):
            preview_dest = _preview_path_for(file)
            if generate_preview(file, preview_dest):
                preview_rel_path = preview_dest.relative_to(settings.data_dir).as_posix()

        dims_source = _preview_path_for(file) if preview_rel_path else file
        try:
            width, height = get_dimensions(dims_source)
        except Exception:
            width, height = None, None

        thumb_dest = thumbnail_path_for(file)
        thumb_rel_path = (
            thumb_dest.relative_to(settings.data_dir).as_posix()
            if generate_thumbnail(dims_source, thumb_dest)
            else None
        )

        photo = Photo(
            filename=file.name,
            original_path=rel_path,
            preview_path=preview_rel_path,
            thumbnail_path=thumb_rel_path,
            taken_at=taken_at,
            width=width,
            height=height,
        )
        db.add(photo)
        new_photos.append(photo)

    db.commit()
    for p in new_photos:
        db.refresh(p)
    return new_photos
