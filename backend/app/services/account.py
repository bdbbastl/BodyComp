"""
Account-Erstellung: legt einen User UND dessen automatisch mitgeliefertes
Client-Profil in einem Schritt an - siehe Design-Spec Abschnitt
"Kontotyp". Wird vom Migrationsscript (Stufe 1) und später vom
Self-Signup-Endpunkt (Stufe 2) gemeinsam genutzt.
"""
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.user import AccountType, User
from app.services.auth import hash_password


def create_account(
    db: Session,
    *,
    email: str,
    password: str,
    display_name: str,
    account_type: AccountType = AccountType.SINGLE,
) -> User:
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name=display_name,
        account_type=account_type,
    )
    db.add(user)
    db.flush()  # user.id wird gebraucht, bevor der Client angelegt wird

    db.add(Client(owner_id=user.id, name=display_name))
    db.commit()
    db.refresh(user)
    return user
