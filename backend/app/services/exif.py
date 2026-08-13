"""EXIF-Auslesung für den Ordner-Sync."""
from datetime import datetime
from pathlib import Path

import piexif
import pillow_heif
from PIL import Image

# Idempotent - registriert HEIC/HEIF bei Pillow, damit Image.open() (Größe,
# EXIF-Fallback unten) auch für iPhone-Fotos funktioniert. Wird hier zur
# Sicherheit unabhängig von der Import-Reihenfolge nochmal aufgerufen
# (siehe auch services/heic.py).
pillow_heif.register_heif_opener()


def get_taken_at(path: Path) -> datetime:
    """Liest DateTimeOriginal aus EXIF; fällt auf Datei-mtime zurück,
    wenn kein EXIF-Tag vorhanden ist (z.B. Screenshot, bearbeitetes Bild)."""
    try:
        exif_dict = piexif.load(str(path))
        raw = exif_dict.get("Exif", {}).get(piexif.ExifIFD.DateTimeOriginal)
        if raw:
            # EXIF-Format: "YYYY:MM:DD HH:MM:SS"
            return datetime.strptime(raw.decode(), "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass

    # piexif liest nur JPEG/TIFF-Container zuverlässig - bei HEIC (und
    # gelegentlich anderen Formaten) über Pillows eigenen EXIF-Reader
    # nachfassen, bevor auf die Datei-mtime zurückgefallen wird.
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            exif_ifd = exif.get_ifd(0x8769)  # Exif-IFD-Pointer
            raw = exif_ifd.get(36867) or exif.get(36867)  # DateTimeOriginal
            if raw:
                if isinstance(raw, bytes):
                    raw = raw.decode()
                return datetime.strptime(raw, "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass

    return datetime.fromtimestamp(path.stat().st_mtime)


def get_dimensions(path: Path) -> tuple[int, int]:
    with Image.open(path) as img:
        return img.width, img.height
