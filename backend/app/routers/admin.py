"""Master-Admin-Bereich - siehe Design-Spec "Master-Admin-Dashboard".
Alle Routen hinter require_admin (app/routers/auth.py)."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.checkin_submission import CheckinSubmission
from app.models.client import Client
from app.models.day_log import DayLog
from app.models.photo import Photo
from app.models.user import AccountType, User
from app.routers.auth import require_admin
from app.schemas.admin import (
    AdminAccountDetailOut,
    AdminAccountOut,
    AdminClientSummaryOut,
    AdminOverviewOut,
    AdminSetActiveRequest,
)

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])

# Wie active/inactive bestimmt wird - konsistent mit dem 14-Tage-Fenster
# aus der Design-Spec. "never" (kein last_activity_at) wird separat
# behandelt, siehe _activity_status.
ACTIVITY_WINDOW_DAYS = 14


def _activity_status(last_activity_at: datetime | None) -> str:
    if last_activity_at is None:
        return "never"
    cutoff = datetime.now(timezone.utc) - timedelta(days=ACTIVITY_WINDOW_DAYS)
    compare_at = last_activity_at
    if compare_at.tzinfo is None:
        compare_at = compare_at.replace(tzinfo=timezone.utc)
    return "active" if compare_at >= cutoff else "inactive"


def _last_activity_for_client_ids(db: Session, client_ids: list[int]) -> dict[int, datetime]:
    """Jüngster Zeitstempel je client_id über DayLog/Photo/CheckinSubmission
    hinweg - drei separate MAX()-Queries statt einem UNION, weil die
    Datenmenge klein ist und das lesbarer bleibt (siehe Design-Spec)."""
    if not client_ids:
        return {}
    result: dict[int, datetime] = {}

    def _merge(rows):
        for client_id, ts in rows:
            if ts is None:
                continue
            # Postgres liefert TIMESTAMP-Spalten (Photo.taken_at,
            # CheckinSubmission.submitted_at) ohne tzinfo zurück, obwohl sie
            # als UTC gemeint sind - im Gegensatz zu den oben schon manuell
            # tz-aware gemachten DayLog-Werten. Ohne diese Normalisierung
            # crasht der Vergleich unten mit "can't compare offset-naive
            # and offset-aware datetimes" (auf SQLite in Tests nicht
            # aufgefallen, da dort beide Seiten konsistent behandelt
            # wurden - Bug erst in Produktion/Postgres sichtbar geworden).
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if client_id not in result or ts > result[client_id]:
                result[client_id] = ts

    day_log_rows = (
        db.query(DayLog.client_id, func.max(DayLog.date))
        .filter(DayLog.client_id.in_(client_ids))
        .group_by(DayLog.client_id)
        .all()
    )
    _merge(
        (client_id, datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc))
        for client_id, d in day_log_rows
        if d is not None
    )

    photo_rows = (
        db.query(Photo.client_id, func.max(Photo.taken_at))
        .filter(Photo.client_id.in_(client_ids))
        .group_by(Photo.client_id)
        .all()
    )
    _merge(photo_rows)

    checkin_rows = (
        db.query(CheckinSubmission.client_id, func.max(CheckinSubmission.submitted_at))
        .filter(CheckinSubmission.client_id.in_(client_ids))
        .group_by(CheckinSubmission.client_id)
        .all()
    )
    _merge(checkin_rows)

    return result


def _account_out(
    user: User, client_count: int, last_activity_at: datetime | None
) -> AdminAccountOut:
    return AdminAccountOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        account_type=user.account_type,
        created_at=user.created_at,
        subscription_status=user.subscription_status,
        subscription_tier=user.subscription_tier,
        client_count=client_count,
        is_active=user.is_active,
        is_admin=user.is_admin,
        last_activity_at=last_activity_at,
        activity_status=_activity_status(last_activity_at),
    )


@router.get("/overview", response_model=AdminOverviewOut)
def overview(db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    total_accounts = db.query(func.count(User.id)).scalar() or 0
    single_accounts = (
        db.query(func.count(User.id)).filter(User.account_type == AccountType.SINGLE).scalar() or 0
    )
    coach_accounts = (
        db.query(func.count(User.id)).filter(User.account_type == AccountType.COACH).scalar() or 0
    )
    active_subscriptions = (
        db.query(func.count(User.id))
        .filter(User.subscription_status.in_(["active", "trialing"]))
        .scalar()
        or 0
    )
    signups_this_week = (
        db.query(func.count(User.id)).filter(User.created_at >= week_ago).scalar() or 0
    )
    signups_this_month = (
        db.query(func.count(User.id)).filter(User.created_at >= month_ago).scalar() or 0
    )

    return AdminOverviewOut(
        total_accounts=total_accounts,
        single_accounts=single_accounts,
        coach_accounts=coach_accounts,
        active_subscriptions=active_subscriptions,
        signups_this_week=signups_this_week,
        signups_this_month=signups_this_month,
    )


@router.get("/accounts", response_model=list[AdminAccountOut])
def list_accounts(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    user_ids = [u.id for u in users]

    client_counts = dict(
        db.query(Client.owner_id, func.count(Client.id))
        .filter(Client.owner_id.in_(user_ids))
        .group_by(Client.owner_id)
        .all()
    )
    client_ids_by_owner: dict[int, list[int]] = {}
    for owner_id, client_id in db.query(Client.owner_id, Client.id).filter(
        Client.owner_id.in_(user_ids)
    ).all():
        client_ids_by_owner.setdefault(owner_id, []).append(client_id)

    all_client_ids = [cid for ids in client_ids_by_owner.values() for cid in ids]
    activity_by_client = _last_activity_for_client_ids(db, all_client_ids)

    results = []
    for user in users:
        owned_client_ids = client_ids_by_owner.get(user.id, [])
        last_activity_at = None
        for cid in owned_client_ids:
            ts = activity_by_client.get(cid)
            if ts is not None and (last_activity_at is None or ts > last_activity_at):
                last_activity_at = ts
        results.append(_account_out(user, client_counts.get(user.id, 0), last_activity_at))
    return results


@router.get("/accounts/{user_id}", response_model=AdminAccountDetailOut)
def get_account(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Account not found")

    clients = db.query(Client).filter(Client.owner_id == user_id).all()
    client_ids = [c.id for c in clients]
    activity_by_client = _last_activity_for_client_ids(db, client_ids)
    photo_counts = dict(
        db.query(Photo.client_id, func.count(Photo.id))
        .filter(Photo.client_id.in_(client_ids))
        .group_by(Photo.client_id)
        .all()
    )

    client_summaries = [
        AdminClientSummaryOut(
            id=c.id,
            name=c.name,
            photo_count=photo_counts.get(c.id, 0),
            last_activity_at=activity_by_client.get(c.id),
        )
        for c in clients
    ]
    last_activity_at = max(
        (s.last_activity_at for s in client_summaries if s.last_activity_at is not None),
        default=None,
    )

    total_checkins = (
        db.query(func.count(CheckinSubmission.id))
        .filter(CheckinSubmission.client_id.in_(client_ids))
        .scalar()
        or 0
    )

    total_storage_bytes, photos_with_unknown_size = (
        db.query(
            func.coalesce(func.sum(Photo.file_size_bytes), 0),
            func.count().filter(Photo.file_size_bytes.is_(None)),
        )
        .filter(Photo.client_id.in_(client_ids))
        .one()
    )

    base = _account_out(user, len(clients), last_activity_at)
    return AdminAccountDetailOut(
        **base.model_dump(),
        clients=client_summaries,
        total_checkins=total_checkins,
        total_storage_bytes=total_storage_bytes,
        photos_with_unknown_size=photos_with_unknown_size,
    )


@router.patch("/accounts/{user_id}", response_model=AdminAccountOut)
def set_account_active(
    user_id: int,
    payload: AdminSetActiveRequest,
    db: Session = Depends(get_db),
    # require_admin läuft hier bewusst ZUSÄTZLICH zur router-weiten
    # dependencies=[Depends(require_admin)] oben - nicht um nochmal zu
    # prüfen (das passiert schon), sondern um den aufgelösten User für
    # den Selbst-Deaktivierungs-Check unten zu bekommen. Nicht durch
    # get_current_user ersetzen, das würde die Admin-Prüfung für diese
    # Route implizit von der Router-Ebene abkoppeln.
    current_admin: User = Depends(require_admin),
):
    if user_id == current_admin.id:
        raise HTTPException(400, "Cannot deactivate your own account")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Account not found")

    user.is_active = payload.is_active
    db.commit()
    db.refresh(user)

    client_count = db.query(func.count(Client.id)).filter(Client.owner_id == user_id).scalar() or 0
    client_ids = [row[0] for row in db.query(Client.id).filter(Client.owner_id == user_id).all()]
    activity = _last_activity_for_client_ids(db, client_ids)
    last_activity_at = max(activity.values(), default=None)
    return _account_out(user, client_count, last_activity_at)
