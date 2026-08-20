"""Datei-Cleanup für Fotos - gemeinsam genutzt von routers/photos.py
(Einzel-/Tages-Löschung) und routers/clients.py (Komplett-Löschung eines
Klienten, siehe Design-Spec "Coach-Onboarding-Tour v2" Teil 4)."""
from app.core.config import settings
from app.models.photo import Photo
from app.services.storage_sync import delete_remote, ensure_local


def delete_photo_files(photo: Photo) -> None:
    """Entfernt alle mit dem Foto verknüpften Dateien von der Platte
    (Original, HEIC-Vorschau, normalisierte Version, Thumbnail).
    Fehlende Dateien werden stillschweigend übersprungen (z.B. bei
    inkonsistentem Zustand)."""
    for rel_path in (photo.original_path, photo.preview_path, photo.normalized_path, photo.thumbnail_path):
        if not rel_path:
            continue
        ensure_local(rel_path)
        file = settings.data_dir / rel_path
        if file.exists():
            file.unlink()
        delete_remote(rel_path)
