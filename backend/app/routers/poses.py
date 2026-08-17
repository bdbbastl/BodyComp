"""Posen-Konfiguration pro Kunde: anlegen, umbenennen, löschen."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.client import Client
from app.models.pose import Pose
from app.routers.clients import get_owned_client
from app.schemas.pose import PoseCreate, PoseOut, PoseUpdate

router = APIRouter(prefix="/api/clients/{client_id}/poses", tags=["poses"])


@router.get("", response_model=list[PoseOut])
def list_poses(client_row: Client = Depends(get_owned_client), db: Session = Depends(get_db)):
    return (
        db.query(Pose)
        .filter(Pose.client_id == client_row.id)
        .order_by(Pose.sort_order, Pose.id)
        .all()
    )


@router.post("", response_model=PoseOut, status_code=201)
def create_pose(
    payload: PoseCreate, client_row: Client = Depends(get_owned_client), db: Session = Depends(get_db)
):
    exists = (
        db.query(Pose)
        .filter(Pose.client_id == client_row.id, func.lower(Pose.name) == payload.name.lower())
        .first()
    )
    if exists:
        raise HTTPException(409, "A pose with this name already exists")
    max_order = (
        db.query(func.max(Pose.sort_order)).filter(Pose.client_id == client_row.id).scalar() or 0
    )
    pose = Pose(client_id=client_row.id, name=payload.name, sort_order=max_order + 1)
    db.add(pose)
    db.commit()
    db.refresh(pose)
    return pose


def _get_owned_pose(pose_id: int, client_row: Client, db: Session) -> Pose:
    pose = db.query(Pose).filter(Pose.id == pose_id, Pose.client_id == client_row.id).first()
    if not pose:
        raise HTTPException(404, "Pose not found")
    return pose


@router.patch("/{pose_id}", response_model=PoseOut)
def update_pose(
    pose_id: int,
    payload: PoseUpdate,
    client_row: Client = Depends(get_owned_client),
    db: Session = Depends(get_db),
):
    pose = _get_owned_pose(pose_id, client_row, db)
    if payload.name is not None:
        pose.name = payload.name
    if payload.sort_order is not None:
        pose.sort_order = payload.sort_order
    db.commit()
    db.refresh(pose)
    return pose


@router.delete("/{pose_id}", status_code=204)
def delete_pose(
    pose_id: int, client_row: Client = Depends(get_owned_client), db: Session = Depends(get_db)
):
    pose = _get_owned_pose(pose_id, client_row, db)
    # Fotos bleiben erhalten, pose_id wird via ondelete=SET NULL genullt
    # -> Bilder landen wieder im "Unprocessed"-Filter für diese Pose.
    db.delete(pose)
    db.commit()
