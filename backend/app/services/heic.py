"""
HEIC/HEIF-Unterstützung (iPhone-Standardformat).

Weder Browser noch OpenCV können HEIC nativ dekodieren. Für jede HEIC-
Datei wird daher beim Ordner-Sync einmalig eine JPEG-Vorschau erzeugt
(Photo.preview_path) - diese wird sowohl fürs Anzeigen im Frontend als
auch als Eingabe für die MediaPipe-Normalisierung verwendet. Die
Originaldatei bleibt unangetastet liegen (Backup/Referenz).
"""
from pathlib import Path

import pillow_heif
from PIL import Image

pillow_heif.register_heif_opener()

HEIC_EXTENSIONS = {".heic", ".heif"}

PREVIEW_JPEG_QUALITY = 92


def is_heic(path: Path) -> bool:
    return path.suffix.lower() in HEIC_EXTENSIONS


def generate_preview(source_path: Path, dest_path: Path) -> bool:
    """Konvertiert eine HEIC-Datei nach JPEG. Gibt False zurück (statt zu
    werfen) wenn die Datei nicht dekodiert werden kann, damit ein
    einzelnes defektes Foto den restlichen Ordner-Sync nicht blockiert."""
    try:
        with Image.open(source_path) as img:
            # HEIC kann EXIF-Orientation enthalten, die Pillow beim reinen
            # .convert() nicht automatisch anwendet.
            img = _apply_exif_orientation(img)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            img.convert("RGB").save(dest_path, "JPEG", quality=PREVIEW_JPEG_QUALITY)
        return True
    except Exception:
        return False


def _apply_exif_orientation(img: Image.Image) -> Image.Image:
    from PIL import ImageOps

    return ImageOps.exif_transpose(img) or img
