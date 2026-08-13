"""
Kunden-Verwaltung: Liste/Anlegen/Bearbeiten der Client-Profile eines
Accounts, plus die zentrale `get_owned_client`-Dependency, die JEDER
client-scoped Router (photos/poses/day_logs/comparisons) importiert, um
sicherzustellen, dass ein Account nie auf fremde Kunden zugreifen kann.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
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


@router.get("", response_model=list[ClientOut])
def list_clients(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return (
        db.query(Client)
        .filter(Client.owner_id == current_user.id)
        .order_by(Client.created_at)
        .all()
    )


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
    return client_row


@router.get("/{client_id}", response_model=ClientOut)
def get_client(client_row: Client = Depends(get_owned_client)):
    return client_row


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
    return client_row
