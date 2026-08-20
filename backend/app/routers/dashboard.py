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
    ActivityItem,
    CoachDashboardSummary,
    DayCount,
    NeedsAttentionClient,
    PendingCheckinSummary,
    WeekCount,
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

    # --- activity_feed: letzte 5 Ereignisse (Check-in eingereicht/reviewed,
    # neuer Klient), neueste zuerst. Reine Aggregation, kein neues Modell.
    all_checkins = (
        db.query(CheckinSubmission)
        .filter(
            CheckinSubmission.client_id.in_(client_ids),
            CheckinSubmission.submitted_at >= now - timedelta(weeks=6),
        )
        .all()
    )

    def _aware(dt: datetime) -> datetime:
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

    activity_events: list[ActivityItem] = []
    for row in all_checkins:
        activity_events.append(
            ActivityItem(
                type="checkin_submitted",
                client_id=row.client_id,
                client_name=client_names[row.client_id],
                timestamp=row.submitted_at,
            )
        )
        if row.status == CheckinStatus.REVIEWED and row.reviewed_at is not None:
            activity_events.append(
                ActivityItem(
                    type="checkin_reviewed",
                    client_id=row.client_id,
                    client_name=client_names[row.client_id],
                    timestamp=row.reviewed_at,
                )
            )
    for c in clients:
        activity_events.append(
            ActivityItem(
                type="client_added",
                client_id=c.id,
                client_name=c.name,
                timestamp=c.created_at,
            )
        )
    activity_events.sort(key=lambda e: _aware(e.timestamp), reverse=True)
    activity_feed = activity_events[:5]

    # --- active_clients_last_7_days: pro Kalendertag (UTC), wie viele
    # Klienten an dem Tag einen Check-in eingereicht ODER ein Foto
    # aufgenommen haben. Älteste zuerst, heute zuletzt.
    photo_rows_7d = (
        db.query(Photo.client_id, Photo.taken_at)
        .filter(Photo.client_id.in_(client_ids), Photo.taken_at >= now - timedelta(days=7))
        .all()
    )
    active_clients_last_7_days: list[DayCount] = []
    for offset in range(6, -1, -1):
        day_start = (now - timedelta(days=offset)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        day_end = day_start + timedelta(days=1)
        active_ids = {
            row.client_id
            for row in all_checkins
            if day_start <= _aware(row.submitted_at) < day_end
        }
        active_ids |= {
            cid for cid, taken_at in photo_rows_7d if day_start <= _aware(taken_at) < day_end
        }
        active_clients_last_7_days.append(
            DayCount(date=day_start.date().isoformat(), count=len(active_ids))
        )

    # --- checkins_per_week: letzte 6 Kalenderwochen (Montag-Start), Anzahl
    # eingereichter Check-ins über alle Klienten.
    current_week_start = now.date() - timedelta(days=now.weekday())
    checkins_per_week: list[WeekCount] = []
    for weeks_ago in range(5, -1, -1):
        week_start = current_week_start - timedelta(weeks=weeks_ago)
        week_end = week_start + timedelta(days=7)
        count = sum(
            1 for row in all_checkins if week_start <= row.submitted_at.date() < week_end
        )
        checkins_per_week.append(WeekCount(week_start=week_start.isoformat(), count=count))

    return CoachDashboardSummary(
        pending_checkins=pending_checkins,
        needs_attention=needs_attention,
        week_stats=WeekStats(
            checkins=checkins_this_week,
            photos=photos_this_week,
            active_clients=len(active_client_ids),
        ),
        active_clients_last_7_days=active_clients_last_7_days,
        checkins_per_week=checkins_per_week,
        activity_feed=activity_feed,
    )
