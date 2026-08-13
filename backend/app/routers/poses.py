"""Posen-Konfiguration: anlegen, umbenennen, löschen (Einstellungsseite)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.pose import Pose
from app.schemas.pose import PoseCreate, PoseOut, PoseUpdate

router = APIRouter(prefix="/api/poses", tags=["poses"])


@router.get("", response_model=list[PoseOut])
def list_poses(db: Session = Depends(get_db)):
    return db.query(Pose).order_by(Pose.sort_order, Pose.id).all()


@router.post("", response_model=PoseOut, status_code=201)
def create_pose(payload: PoseCreate, db: Session = Depends(get_db)):
    if db.query(Pose).filter(func.lower(Pose.name) == payload.name.lower()).first():
        raise HTTPException(409, "Pose mit diesem Namen existiert bereits")
    max_order = db.query(func.max(Pose.sort_order)).scalar() or 0
    pose = Pose(name=payload.name, sort_order=max_order + 1)
    db.add(pose)
    db.commit()
    db.refresh(pose)
    return pose


@router.patch("/{pose_id}", response_model=PoseOut)
def update_pose(pose_id: int, payload: PoseUpdate, db: Session = Depends(get_db)):
    pose = db.get(Pose, pose_id)
    if not pose:
        raise HTTPException(404, "Pose nicht gefunden")
    if payload.name is not None:
        pose.name = payload.name
    if payload.sort_order is not None:
        pose.sort_order = payload.sort_order
    db.commit()
    db.refresh(pose)
    return pose


@router.delete("/{pose_id}", status_code=204)
def delete_pose(pose_id: int, db: Session = Depends(get_db)):
    pose = db.get(Pose, pose_id)
    if not pose:
        raise HTTPException(404, "Pose nicht gefunden")
    # Fotos bleiben erhalten, pose_id wird via ondelete=SET NULL genullt
    # -> Bilder landen wieder im "Unprocessed"-Filter für diese Pose.
    db.delete(pose)
    db.commit()
