"""
Kleine JPEG-Vorschaubilder für Grid-Ansichten (Timeline, Import-Queue).

Die Originale sind unkomprimierte Handyfotos (z.B. 4284x5712px, mehrere
MB). Die Timeline/Import-Grids zeigen sie nur ein paar Zoll groß an,
luden dafür aber bisher die vollen Originaldateien - bei Dutzenden
gleichzeitig sichtbaren Fotos war das der Haupttreiber für die spürbar
lange Ladezeit. Ein ~500px-Thumbnail (üblicherweise <50KB) reicht für die
Grid-Darstellung völlig aus; die Lightbox/Compare-Ansichten laden weiterhin
das Original bzw. die normalisierte Version in voller Auflösung.
"""
from pathlib import Path

from PIL import Image, ImageOps

THUMBNAIL_MAX_EDGE = 500
THUMBNAIL_QUALITY = 80


def thumbnail_path_for(source: Path) -> Path:
    """Konvention: Thumbnail liegt direkt neben der Quelldatei, gleicher
    Name + .thumb.jpg-Suffix - bleibt so beim Verschieben (Unprocessed ->
    Processed) leicht zusammen mit dem Original auffindbar, analog zu
    services/heic.py's .preview.jpg-Konvention."""
    return source.parent / f"{source.name}.thumb.jpg"


def generate_thumbnail(source_path: Path, dest_path: Path) -> bool:
    """Erzeugt ein verkleinertes JPEG unter dest_path. Gibt False zurück
    (statt zu werfen) bei nicht lesbaren/beschädigten Bildern - ein
    fehlendes Thumbnail ist nicht kritisch, das Frontend fällt dann auf
    das Originalbild zurück."""
    try:
        with Image.open(source_path) as img:
            # Handyfotos speichern die Ausrichtung meist nur als EXIF-
            # "Orientation"-Tag, die Pixel selbst bleiben im Sensor-
            # Rohformat (oft Querformat, auch bei "Hochkant" fotografiert).
            # Browser wenden dieses Tag beim <img>-Rendering automatisch
            # an, PIL beim Öffnen NICHT - ohne exif_transpose() landet das
            # rohe (falsch gedrehte) Rechteck ungefiltert im Thumbnail.
            # exif_transpose() dreht/spiegelt die Pixel entsprechend und
            # entfernt den Tag danach, damit nichts doppelt gedreht wird.
            img = ImageOps.exif_transpose(img)
            img = img.convert("RGB")
            width, height = img.size
            scale = THUMBNAIL_MAX_EDGE / max(width, height)
            if scale < 1:
                img = img.resize(
                    (max(1, int(width * scale)), max(1, int(height * scale))), Image.LANCZOS
                )
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(dest_path, format="JPEG", quality=THUMBNAIL_QUALITY)
        return True
    except Exception:
        return False
