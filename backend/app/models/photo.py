"""
Photo = ein einzelnes Bild aus dem überwachten Ordner, gehört zu GENAU
EINEM Client.

Lifecycle:
1. Ordner-Sync (services/folder_sync.py) findet neue Datei in
   photos_incoming/, liest EXIF-Datum aus, legt Photo-Row mit
   status=UNPROCESSED an (pose_id ist NULL).
2. Nutzer ordnet in der "Unprocessed"-Ansicht die Pose manuell zu
   (+ optional Gewicht für den Tag). Datei wird nach photos_processed/
   verschoben, status -> PROCESSED.
3. Als Nebeneffekt der Zuordnung läuft die MediaPipe-Normalisierung
   (services/pose_normalization.py) und befüllt normalized_path.
"""
import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ProcessingStatus(str, enum.Enum):
    UNPROCESSED = "unprocessed"
    PROCESSED = "processed"
    # Normalisierung fehlgeschlagen (z.B. keine Landmarks erkannt) -
    # Bild bleibt trotzdem "processed" (Pose ist zugeordnet), nur
    # Overlay-Vergleich ist dafür nicht verfügbar.
    NORMALIZATION_FAILED = "normalization_failed"


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Dateiname wie im Quellordner gefunden (informativ, für Debugging).
    filename: Mapped[str] = mapped_column(String(255), nullable=False)

    # Pfad zur Originaldatei, relativ zu settings.data_dir, damit die DB
    # portabel bleibt (z.B. beim Umzug auf einen anderen Rechner/Cloud-Mount).
    original_path: Mapped[str] = mapped_column(String(1000), nullable=False, unique=True)

    # Pfad zur normalisierten Version (siehe pose_normalization.py),
    # NULL solange nicht normalisiert bzw. wenn Normalisierung fehlschlug.
    normalized_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # JPEG-Vorschau für Formate, die Browser/OpenCV nicht direkt lesen
    # können (aktuell: HEIC/HEIF von iPhones, siehe services/heic.py).
    # NULL für ohnehin browserfähige Formate (JPEG/PNG) - dann wird direkt
    # original_path verwendet. Wird sowohl fürs Anzeigen im Frontend als
    # auch als Eingabe für die MediaPipe-Normalisierung genutzt (OpenCV
    # kann ebenfalls kein HEIC dekodieren).
    preview_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Kleines JPEG (max. ~500px Kante) für Grid-Ansichten (Timeline,
    # Import-Queue) - die Originale sind Handyfotos mit mehreren MB/
    # mehreren tausend Pixel Kante, das direkte Laden von Dutzenden
    # Originalen für ein paar Zoll große Thumbnails war der Haupttreiber
    # für die lange Ladezeit der Timeline. NULL bis generiert (Backfill
    # via POST /api/photos/backfill-thumbnails für Bestandsfotos, sonst
    # automatisch bei Sync/Upload/Zuordnung).
    thumbnail_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Aufnahmedatum aus EXIF (DateTimeOriginal). Fallback: Datei-mtime,
    # falls kein EXIF-Tag vorhanden ist (siehe services/exif.py).
    taken_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus), default=ProcessingStatus.UNPROCESSED, nullable=False, index=True
    )

    pose_id: Mapped[int | None] = mapped_column(
        ForeignKey("poses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    pose: Mapped["Pose"] = relationship(back_populates="photos")  # noqa: F821

    day_log_id: Mapped[int | None] = mapped_column(
        ForeignKey("day_logs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    day_log: Mapped["DayLog"] = relationship(back_populates="photos")  # noqa: F821

    checkin_submission_id: Mapped[int | None] = mapped_column(
        ForeignKey("checkin_submissions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    checkin_submission: Mapped["CheckinSubmission"] = relationship(  # noqa: F821
        back_populates="photos"
    )

    # Von MediaPipe erkannte Landmark-Koordinaten (JSON-serialisiert),
    # gecacht damit eine erneute Normalisierung (z.B. nach Crop-Regel-
    # Änderung) nicht erneut die komplette Pose-Detection laufen muss.
    landmarks_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Größe der Originaldatei in Bytes, direkt nach dem finalen
    # Schreiben/Komprimieren erfasst (services/folder_sync.py) - für den
    # Speicherverbrauch im Master-Admin-Bereich. NULL für Fotos, die vor
    # Einführung dieser Spalte synchronisiert wurden (kein rückwirkendes
    # Backfill, siehe Design-Spec "Master-Admin: Account-Detail-
    # Kennzahlen" Abschnitt b).
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return (
            f"<Photo id={self.id} filename={self.filename!r} "
            f"status={self.status} pose_id={self.pose_id}>"
        )
