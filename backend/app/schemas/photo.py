from datetime import datetime

from pydantic import BaseModel, computed_field, field_validator

from app.models.photo import ProcessingStatus
from app.utils.weight import parse_weight_kg


class PhotoOut(BaseModel):
    id: int
    filename: str
    original_path: str
    preview_path: str | None
    normalized_path: str | None
    thumbnail_path: str | None
    taken_at: datetime
    status: ProcessingStatus
    pose_id: int | None
    day_log_id: int | None
    width: int | None
    height: int | None

    class Config:
        from_attributes = True

    @computed_field
    @property
    def display_path(self) -> str:
        """Der Pfad, den das Frontend fürs <img>-Tag verwenden soll: die
        JPEG-Vorschau bei Formaten, die Browser nicht direkt rendern
        können (aktuell HEIC/HEIF), sonst original_path."""
        return self.preview_path or self.original_path

    @computed_field
    @property
    def thumb_path(self) -> str:
        """Kleines Vorschaubild für Grid-Ansichten (Timeline, Import-
        Queue) - fällt auf display_path zurück, solange kein Thumbnail
        generiert wurde (z.B. kurz vor Abschluss des Backfills)."""
        return self.thumbnail_path or self.display_path


class PhotoUnprocessedOut(PhotoOut):
    """Wie PhotoOut, plus optionaler Pose-Vorschlag (siehe
    services/pose_suggestion.py) für die Unprocessed-Ansicht."""

    suggested_pose_id: int | None = None


class _WeightValidatorMixin:
    @field_validator("weight_kg", mode="before")
    @classmethod
    def _parse_weight(cls, v):
        if v is None or isinstance(v, (int, float)):
            return v
        try:
            return parse_weight_kg(v)
        except ValueError:
            raise ValueError("weight_kg must be a number (comma or dot as decimal separator)")


class PhotoAssign(_WeightValidatorMixin, BaseModel):
    """Payload für die manuelle Zuordnung eines Unprocessed-Bilds."""

    pose_id: int
    weight_kg: float | None = None  # optional: aktualisiert/erstellt DayLog des taken_at-Datums


class PhotoBulkAssignItem(_WeightValidatorMixin, BaseModel):
    photo_id: int
    pose_id: int
    weight_kg: float | None = None


class PhotoBulkAssign(BaseModel):
    """Payload für die Massenzuordnung - nur Fotos mit gesetzter Pose
    werden übergeben, alle anderen bleiben unverändert in der Queue."""

    items: list[PhotoBulkAssignItem]


class PhotoRepose(BaseModel):
    """Payload für die nachträgliche Pose-Korrektur eines bereits
    zugeordneten Fotos (z.B. in der Timeline)."""

    pose_id: int
