"""
Account-Erstellung: legt einen User UND dessen automatisch mitgeliefertes
Client-Profil in einem Schritt an - siehe Design-Spec Abschnitt
"Kontotyp". Wird vom Migrationsscript (Stufe 1) und später vom
Self-Signup-Endpunkt (Stufe 2) gemeinsam genutzt.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.client import Client
from app.models.email_token import EmailToken, EmailTokenPurpose
from app.models.user import AccountType, User
from app.services.auth import create_email_token, hash_email_token, hash_password
from app.services.email import send_password_reset_email


def create_account(
    db: Session,
    *,
    email: str,
    password: str | None,
    display_name: str,
    account_type: AccountType = AccountType.SINGLE,
) -> User:
    user = User(
        email=email,
        password_hash=hash_password(password) if password is not None else None,
        display_name=display_name,
        account_type=account_type,
    )
    db.add(user)
    db.flush()  # user.id wird gebraucht, bevor der Client angelegt wird

    db.add(Client(owner_id=user.id, name=display_name))
    db.commit()
    db.refresh(user)
    return user


def trigger_password_reset(db: Session, user: User) -> None:
    """Erzeugt einen Reset-Token und verschickt die Standard-Reset-Mail -
    gemeinsame Logik für den öffentlichen forgot-password-Endpunkt
    (routers/auth.py) und den Admin-Endpunkt POST
    /admin/accounts/{id}/send-password-reset (siehe Design-Spec
    "Master-Admin: Signup-Trend & Admin-Aktionen" Abschnitt 2a). Kein
    Enumeration-Schutz nötig - der Aufrufer ist entweder der öffentliche
    Endpunkt (prüft selbst, ob der Account existiert) oder der bereits
    eingeloggte Admin (kennt den Account schon)."""
    raw_token = create_email_token(user_id=user.id, purpose=EmailTokenPurpose.RESET_PASSWORD.value)
    db.add(
        EmailToken(
            user_id=user.id,
            token_hash=hash_email_token(raw_token),
            purpose=EmailTokenPurpose.RESET_PASSWORD,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )
    db.commit()
    reset_url = f"{settings.frontend_base_url}/reset-password?token={raw_token}"
    send_password_reset_email(to=user.email, reset_url=reset_url)
