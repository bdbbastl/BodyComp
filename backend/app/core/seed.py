"""Legt die 7 Standard-Posen an, falls die Tabelle leer ist (Erststart)."""
from sqlalchemy.orm import Session

from app.models.pose import Pose

DEFAULT_POSES = [
    "Front Double Biceps",
    "Front Lat Spread",
    "Side Chest",
    "Back Double Biceps",
    "Back Lat Spread",
    "Side Triceps",
    "Most Muscular",
]


def seed_default_poses(db: Session) -> None:
    if db.query(Pose).count() > 0:
        return
    for i, name in enumerate(DEFAULT_POSES):
        db.add(Pose(name=name, sort_order=i))
    db.commit()
