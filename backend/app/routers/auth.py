"""Login/Logout via signiertes, httpOnly Session-Cookie - siehe
Design-Spec Abschnitt "Authentifizierung"."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import RateLimiter
from app.models.email_token import EmailToken, EmailTokenPurpose
from app.models.user import AccountType, User
from app.schemas.auth import LoginRequest, UserOut
from app.schemas.signup import ForgotPasswordRequest, SignupRequest
from app.services.account import create_account
from app.services.auth import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    create_email_token,
    create_session_token,
    hash_email_token,
    verify_email_token_signature,
    verify_password,
    verify_session_token,
)
from app.services.email import send_verification_email

router = APIRouter(prefix="/api/auth", tags=["auth"])

signup_rate_limit = RateLimiter(max_requests=5, window_seconds=3600)
login_rate_limit = RateLimiter(max_requests=10, window_seconds=3600)
resend_verification_rate_limit = RateLimiter(max_requests=5, window_seconds=3600)


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
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(login_rate_limit),
):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "E-Mail oder Passwort falsch")
    if user.email_verified_at is None:
        raise HTTPException(403, "Bitte bestätige zuerst deine E-Mail-Adresse")

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


@router.post("/signup", response_model=UserOut, status_code=201)
def signup(
    payload: SignupRequest,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(signup_rate_limit),
):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(409, "E-Mail-Adresse ist bereits registriert")

    user = create_account(
        db, email=payload.email, password=payload.password, display_name=payload.display_name
    )
    user.privacy_accepted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    raw_token = create_email_token(user_id=user.id, purpose=EmailTokenPurpose.VERIFY_EMAIL.value)
    db.add(EmailToken(
        user_id=user.id,
        token_hash=hash_email_token(raw_token),
        purpose=EmailTokenPurpose.VERIFY_EMAIL,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    ))
    db.commit()

    verify_url = f"{settings.frontend_base_url}/verify-email?token={raw_token}"
    send_verification_email(to=user.email, verify_url=verify_url)

    return user


@router.get("/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    payload = verify_email_token_signature(token, max_age_seconds=60 * 60 * 24)
    if payload is None or payload.get("purpose") != EmailTokenPurpose.VERIFY_EMAIL.value:
        raise HTTPException(400, "Link ist ungültig oder abgelaufen")

    token_row = (
        db.query(EmailToken)
        .filter(
            EmailToken.user_id == payload["user_id"],
            EmailToken.token_hash == hash_email_token(token),
            EmailToken.purpose == EmailTokenPurpose.VERIFY_EMAIL,
            EmailToken.used_at.is_(None),
        )
        .first()
    )
    if token_row is None:
        raise HTTPException(400, "Link ist ungültig, abgelaufen oder bereits verwendet")

    user = db.get(User, payload["user_id"])
    user.email_verified_at = datetime.now(timezone.utc)
    token_row.used_at = datetime.now(timezone.utc)
    db.commit()
    return {"verified": True}


@router.post("/resend-verification", status_code=204)
def resend_verification(
    payload: ForgotPasswordRequest,  # gleiche Shape ({email}), wiederverwendet
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(resend_verification_rate_limit),
):
    user = db.query(User).filter(User.email == payload.email).first()
    if user is not None and user.email_verified_at is None:
        raw_token = create_email_token(user_id=user.id, purpose=EmailTokenPurpose.VERIFY_EMAIL.value)
        db.add(EmailToken(
            user_id=user.id,
            token_hash=hash_email_token(raw_token),
            purpose=EmailTokenPurpose.VERIFY_EMAIL,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        ))
        db.commit()
        verify_url = f"{settings.frontend_base_url}/verify-email?token={raw_token}"
        send_verification_email(to=user.email, verify_url=verify_url)
    # immer 204, unabhängig davon ob der Account existiert (kein Enumeration-Leak)
