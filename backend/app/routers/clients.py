"""
Kunden-Verwaltung: Liste/Anlegen/Bearbeiten der Client-Profile eines
Accounts, plus die zentrale `get_owned_client`-Dependency, die JEDER
client-scoped Router (photos/poses/day_logs/comparisons) importiert, um
sicherzustellen, dass ein Account nie auf fremde Kunden zugreifen kann.
"""
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.seed import seed_default_poses_for_client
from app.models.client import Client
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.client import ClientCreate, ClientOut, ClientUpdate

router = APIRouter(prefix="/api/clients", tags=["clients"])


def get_owned_client(
    client_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Client:
    """Lädt den Client NUR, wenn er dem eingeloggten Account gehört -
    sonst 404 (nicht 403), damit die API nicht mal verrät, ob eine
    fremde Kunden-ID überhaupt existiert. Wird von jedem client-scoped
    Endpunkt als Dependency genutzt."""
    client_row = (
        db.query(Client)
        .filter(Client.id == client_id, Client.owner_id == current_user.id)
        .first()
    )
    if client_row is None:
        raise HTTPException(404, "Kunde nicht gefunden")
    return client_row


def _client_row_to_out(client_row: Client, photo_count: int, last_activity_dt, pending_checkins_count: int = 0) -> ClientOut:
    """Reine Mapping-Funktion, keine DB-Zugriffe - Aggregation liegt beim
    Aufrufer (Einzelabfrage in `_to_client_out`, gebatcht in `list_clients`),
    damit beide Pfade dieselbe Feld-Zuordnung nutzen und nicht auseinanderlaufen."""
    return ClientOut(
        id=client_row.id,
        name=client_row.name,
        height_cm=client_row.height_cm,
        birth_date=client_row.birth_date,
        gender=client_row.gender,
        start_date=client_row.start_date,
        created_at=client_row.created_at,
        photo_count=photo_count,
        last_activity=last_activity_dt.date() if last_activity_dt else None,
        pending_checkins_count=pending_checkins_count,
        checkin_token=client_row.checkin_token,
        coach_private_note=client_row.coach_private_note,
        email=client_row.email,
        checkin_reminder_days=client_row.checkin_reminder_days,
    )


def _to_client_out(client_row: Client, db: Session) -> ClientOut:
    from sqlalchemy import func

    from app.models.checkin_submission import CheckinStatus, CheckinSubmission
    from app.models.photo import Photo

    photo_count = (
        db.query(func.count(Photo.id)).filter(Photo.client_id == client_row.id).scalar() or 0
    )
    last_activity_dt = (
        db.query(func.max(Photo.taken_at)).filter(Photo.client_id == client_row.id).scalar()
    )
    pending_checkins_count = (
        db.query(func.count(CheckinSubmission.id))
        .filter(
            CheckinSubmission.client_id == client_row.id,
            CheckinSubmission.status == CheckinStatus.PENDING,
        )
        .scalar()
        or 0
    )
    return _client_row_to_out(client_row, photo_count, last_activity_dt, pending_checkins_count)


@router.get("", response_model=list[ClientOut])
def list_clients(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    from sqlalchemy import func

    from app.models.checkin_submission import CheckinStatus, CheckinSubmission
    from app.models.photo import Photo

    clients = (
        db.query(Client)
        .filter(Client.owner_id == current_user.id)
        .order_by(Client.created_at)
        .all()
    )

    client_ids = [c.id for c in clients]
    stats = dict(
        db.query(Photo.client_id, func.count(Photo.id))
        .filter(Photo.client_id.in_(client_ids))
        .group_by(Photo.client_id)
        .all()
    )
    last_activity = dict(
        db.query(Photo.client_id, func.max(Photo.taken_at))
        .filter(Photo.client_id.in_(client_ids))
        .group_by(Photo.client_id)
        .all()
    )
    pending_checkins = dict(
        db.query(CheckinSubmission.client_id, func.count(CheckinSubmission.id))
        .filter(
            CheckinSubmission.client_id.in_(client_ids),
            CheckinSubmission.status == CheckinStatus.PENDING,
        )
        .group_by(CheckinSubmission.client_id)
        .all()
    )

    return [
        _client_row_to_out(
            c, stats.get(c.id, 0), last_activity.get(c.id), pending_checkins.get(c.id, 0)
        )
        for c in clients
    ]


@router.post("", response_model=ClientOut, status_code=201)
def create_client(
    payload: ClientCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    client_row = Client(owner_id=current_user.id, **payload.model_dump())
    db.add(client_row)
    db.commit()
    db.refresh(client_row)
    seed_default_poses_for_client(db, client_row.id)
    return _to_client_out(client_row, db)


@router.get("/{client_id}", response_model=ClientOut)
def get_client(client_row: Client = Depends(get_owned_client), db: Session = Depends(get_db)):
    return _to_client_out(client_row, db)


@router.patch("/{client_id}", response_model=ClientOut)
def update_client(
    payload: ClientUpdate,
    client_row: Client = Depends(get_owned_client),
    db: Session = Depends(get_db),
):
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(client_row, field, value)
    db.commit()
    db.refresh(client_row)
    return _to_client_out(client_row, db)


@router.post("/{client_id}/checkin-token/regenerate", response_model=ClientOut)
def regenerate_checkin_token(
    client_row: Client = Depends(get_owned_client), db: Session = Depends(get_db)
):
    """Invalidiert den alten Magic-Link sofort (z.B. falls versehentlich
    geteilt) - siehe Design-Spec Abschnitt "Magic-Link-Mechanismus"."""
    client_row.checkin_token = secrets.token_urlsafe(24)
    db.commit()
    db.refresh(client_row)
    return _to_client_out(client_row, db)
