"""Login/Logout via signiertes, httpOnly Session-Cookie - siehe
Design-Spec Abschnitt "Authentifizierung"."""
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import AccountType, User
from app.schemas.auth import LoginRequest, UserOut
from app.services.auth import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    create_session_token,
    verify_password,
    verify_session_token,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def get_current_user(
    session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI-Dependency: liest das Session-Cookie, validiert Signatur +
    Ablauf, lädt den User. Wirft 401, wenn irgendwas davon fehlschlägt."""
    if session is None:
        raise HTTPException(401, "Nicht eingeloggt")
    user_id = verify_session_token(session)
    if user_id is None:
        raise HTTPException(401, "Nicht eingeloggt")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(401, "Nicht eingeloggt")
    return user


@router.post("/login", response_model=UserOut)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "E-Mail oder Passwort falsch")

    token = create_session_token(user.id)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=True,
    )
    return user


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME, secure=True)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/switch-to-coach", response_model=UserOut)
def switch_to_coach(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Kippt account_type auf `coach`. Legt KEINEN neuen Client an und
    verschiebt keine Daten - der implizite Client existiert seit
    Account-Erstellung bereits (siehe services/account.py), er wird nur
    im Dashboard sichtbar. Siehe Design-Spec Abschnitt "Kontotyp"."""
    current_user.account_type = AccountType.COACH
    db.commit()
    db.refresh(current_user)
    return current_user
