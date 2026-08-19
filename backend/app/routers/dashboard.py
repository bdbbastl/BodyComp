"""Aggregierte Kennzahlen fürs Coach-Dashboard-Widget-Layout - siehe
Design-Spec "Coach-Dashboard: 4-Widget-Layout". Nur auf die eigenen
Klienten des eingeloggten Accounts gescoped (analog zu jedem anderen
Router hier), keine gesonderte account_type-Sperre nötig - für
Single-Accounts liefert der Endpunkt einfach triviale/leere Listen.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.checkin_submission import CheckinStatus, CheckinSubmission
from app.models.client import Client
from app.models.photo import Photo
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.dashboard import (
    CoachDashboardSummary,
    NeedsAttentionClient,
    PendingCheckinSummary,
    WeekStats,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

NEEDS_ATTENTION_THRESHOLD_DAYS = 7


@router.get("/coach-summary", response_model=CoachDashboardSummary)
def coach_summary(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    clients = db.query(Client).filter(Client.owner_id == current_user.id).all()
    client_ids = [c.id for c in clients]
    client_names = {c.id: c.name for c in clients}

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    # --- pending_checkins ---
    pending_rows = (
        db.query(CheckinSubmission)
        .filter(
            CheckinSubmission.client_id.in_(client_ids),
            CheckinSubmission.status == CheckinStatus.PENDING,
        )
        .order_by(CheckinSubmission.submitted_at.desc())
        .all()
    )
    pending_checkins = [
        PendingCheckinSummary(
            id=row.id,
            client_id=row.client_id,
            client_name=client_names[row.client_id],
            submitted_at=row.submitted_at,
            weight_kg=row.weight_kg,
        )
        for row in pending_rows
    ]

    # --- needs_attention: letzte Aktivität = neuestes Foto ODER neuester
    # Check-in je Klient (kombiniert, nicht nur Fotos - siehe Design-Spec).
    last_photo = dict(
        db.query(Photo.client_id, func.max(Photo.taken_at))
        .filter(Photo.client_id.in_(client_ids))
        .group_by(Photo.client_id)
        .all()
    )
    last_checkin = dict(
        db.query(CheckinSubmission.client_id, func.max(CheckinSubmission.submitted_at))
        .filter(CheckinSubmission.client_id.in_(client_ids))
        .group_by(CheckinSubmission.client_id)
        .all()
    )

    needs_attention = []
    for c in clients:
        candidates = [d for d in (last_photo.get(c.id), last_checkin.get(c.id)) if d is not None]
        last_activity_dt = max(candidates) if candidates else None
        if last_activity_dt is not None and last_activity_dt.tzinfo is None:
            last_activity_dt = last_activity_dt.replace(tzinfo=timezone.utc)

        if last_activity_dt is None:
            needs_attention.append(NeedsAttentionClient(
                client_id=c.id, client_name=c.name, days_since_activity=None
            ))
        elif last_activity_dt < now - timedelta(days=NEEDS_ATTENTION_THRESHOLD_DAYS):
            days = (now - last_activity_dt).days
            needs_attention.append(NeedsAttentionClient(
                client_id=c.id, client_name=c.name, days_since_activity=days
            ))
    # None ("nie aktiv") zuerst, danach absteigend nach days_since_activity.
    needs_attention.sort(
        key=lambda entry: (entry.days_since_activity is not None, -(entry.days_since_activity or 0))
    )

    # --- week_stats ---
    checkins_this_week = (
        db.query(func.count(CheckinSubmission.id))
        .filter(
            CheckinSubmission.client_id.in_(client_ids),
            CheckinSubmission.submitted_at >= week_ago,
        )
        .scalar()
        or 0
    )
    photos_this_week = (
        db.query(func.count(Photo.id))
        .filter(Photo.client_id.in_(client_ids), Photo.taken_at >= week_ago)
        .scalar()
        or 0
    )
    active_client_ids = set(
        cid
        for (cid,) in db.query(CheckinSubmission.client_id)
        .filter(
            CheckinSubmission.client_id.in_(client_ids),
            CheckinSubmission.submitted_at >= week_ago,
        )
        .distinct()
        .all()
    ) | set(
        cid
        for (cid,) in db.query(Photo.client_id)
        .filter(Photo.client_id.in_(client_ids), Photo.taken_at >= week_ago)
        .distinct()
        .all()
    )

    return CoachDashboardSummary(
        pending_checkins=pending_checkins,
        needs_attention=needs_attention,
        week_stats=WeekStats(
            checkins=checkins_this_week,
            photos=photos_this_week,
            active_clients=len(active_client_ids),
        ),
    )
