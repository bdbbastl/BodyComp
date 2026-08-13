"""
Comparison-Mode: liefert für eine Pose + zwei Daten die passenden Fotos
(Original- und normalisierte Pfade) für Side-by-Side- und Overlay-Ansicht,
sowie die optionale KI-Judge-Analyse (siehe services/ai_comparison.py).
"""
from datetime import date as date_
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.day_log import DayLog
from app.models.photo import Photo
from app.models.pose import Pose
from app.schemas.photo import PhotoOut
from app.services.ai_comparison import AiComparisonError, compare_photos, compare_photos_all

router = APIRouter(prefix="/api/comparisons", tags=["comparisons"])


def _find_photo(db: Session, pose_id: int, target_date: date_) -> Photo | None:
    return (
        db.query(Photo)
        .filter(Photo.pose_id == pose_id)
        .filter(Photo.taken_at >= target_date)
        .filter(Photo.taken_at < target_date.fromordinal(target_date.toordinal() + 1))
        .first()
    )


@router.get("")
def compare(
    pose_id: int = Query(...),
    date_x: date_ = Query(...),
    date_y: date_ = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, PhotoOut | None]:
    photo_x = _find_photo(db, pose_id, date_x)
    photo_y = _find_photo(db, pose_id, date_y)
    if not photo_x or not photo_y:
        raise HTTPException(404, "Für mindestens eines der Daten existiert kein Foto dieser Pose")
    return {
        "photo_x": PhotoOut.model_validate(photo_x),
        "photo_y": PhotoOut.model_validate(photo_y),
    }


@router.get("/ai-analysis")
def ai_analysis(
    pose_id: int = Query(...),
    date_x: date_ = Query(...),
    date_y: date_ = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """
    Bewusst per GET auf User-Aktion (Button-Klick im Frontend), NICHT
    automatisch beim Auswählen zweier Bilder - jeder Aufruf kostet echte
    API-Tokens. Nutzt die Stufe-2-normalisierten Bilder wenn vorhanden
    (konsistentere Bildausschnitte für den Vergleich), sonst das Original.
    """
    photo_x = _find_photo(db, pose_id, date_x)
    photo_y = _find_photo(db, pose_id, date_y)
    if not photo_x or not photo_y:
        raise HTTPException(404, "Für mindestens eines der Daten existiert kein Foto dieser Pose")

    pose = db.get(Pose, pose_id)
    pose_name = pose.name if pose else "Unbekannte Pose"

    path_x = settings.data_dir / (photo_x.normalized_path or photo_x.preview_path or photo_x.original_path)
    path_y = settings.data_dir / (photo_y.normalized_path or photo_y.preview_path or photo_y.original_path)

    day_log_x = db.query(DayLog).filter(DayLog.date == date_x).first()
    day_log_y = db.query(DayLog).filter(DayLog.date == date_y).first()

    try:
        analysis = compare_photos(
            db=db,
            path_x=path_x,
            path_y=path_y,
            pose_name=pose_name,
            date_x=date_x,
            date_y=date_y,
            weight_x=day_log_x.weight_kg if day_log_x else None,
            weight_y=day_log_y.weight_kg if day_log_y else None,
        )
    except AiComparisonError as exc:
        raise HTTPException(502, str(exc)) from exc

    return {"analysis": analysis}


@router.get("/ai-analysis-all")
def ai_analysis_all(
    date_x: date_ = Query(...),
    date_y: date_ = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """
    "Alle Posen"-Variante: sammelt für jede konfigurierte Pose (in
    Settings-Reihenfolge) das Bildpaar der zwei gewählten Termine - falls
    beide existieren - und lässt Gemini daraus EIN gesamtheitliches Urteil
    fällen (siehe services/ai_comparison.compare_photos_all), statt N
    Einzelbewertungen. Bei bis zu 20 Posen macht das max. 40 Bilder in
    einer Anfrage.
    """
    poses = db.query(Pose).order_by(Pose.sort_order, Pose.id).all()

    pairs: list[tuple[str, Path, Path]] = []
    for pose in poses:
        photo_x = _find_photo(db, pose.id, date_x)
        photo_y = _find_photo(db, pose.id, date_y)
        if not photo_x or not photo_y:
            continue
        path_x = settings.data_dir / (photo_x.normalized_path or photo_x.preview_path or photo_x.original_path)
        path_y = settings.data_dir / (photo_y.normalized_path or photo_y.preview_path or photo_y.original_path)
        pairs.append((pose.name, path_x, path_y))

    if not pairs:
        raise HTTPException(404, "Für keine Pose existieren Fotos an beiden gewählten Terminen")

    day_log_x = db.query(DayLog).filter(DayLog.date == date_x).first()
    day_log_y = db.query(DayLog).filter(DayLog.date == date_y).first()

    try:
        analysis = compare_photos_all(
            db=db,
            pairs=pairs,
            date_x=date_x,
            date_y=date_y,
            weight_x=day_log_x.weight_kg if day_log_x else None,
            weight_y=day_log_y.weight_kg if day_log_y else None,
        )
    except AiComparisonError as exc:
        raise HTTPException(502, str(exc)) from exc

    return {"analysis": analysis}
