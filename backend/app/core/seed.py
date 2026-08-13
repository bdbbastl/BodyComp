"""Legt die 7 Standard-Posen für einen neu angelegten Client an."""
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


def seed_default_poses_for_client(db: Session, client_id: int) -> None:
    for i, name in enumerate(DEFAULT_POSES):
        db.add(Pose(client_id=client_id, name=name, sort_order=i))
    db.commit()
