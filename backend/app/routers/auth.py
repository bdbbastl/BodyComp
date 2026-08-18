"""Login/Logout via signiertes, httpOnly Session-Cookie - siehe
Design-Spec Abschnitt "Authentifizierung"."""
import logging
import shutil
from datetime import datetime, timedelta, timezone

from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import RateLimiter
from app.models.email_token import EmailToken, EmailTokenPurpose
from app.models.user import AccountType, User
from app.schemas.auth import LoginRequest, UserOut
from app.schemas.signup import ChangePasswordRequest, ForgotPasswordRequest, ResetPasswordRequest, SignupRequest
from app.services.account import create_account
from app.services.auth import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    create_email_token,
    create_session_token,
    hash_email_token,
    hash_password,
    verify_email_token_signature,
    verify_password,
    verify_session_token,
)
from app.services.email import (
    send_password_reset_email,
    send_verification_email,
    send_welcome_email,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

signup_rate_limit = RateLimiter(max_requests=5, window_seconds=3600)
login_rate_limit = RateLimiter(max_requests=10, window_seconds=3600)
resend_verification_rate_limit = RateLimiter(max_requests=5, window_seconds=3600)
forgot_password_rate_limit = RateLimiter(max_requests=5, window_seconds=3600)
verify_email_rate_limit = RateLimiter(max_requests=20, window_seconds=3600)
reset_password_rate_limit = RateLimiter(max_requests=20, window_seconds=3600)
change_password_rate_limit = RateLimiter(max_requests=5, window_seconds=3600)


class DeleteAccountRequest(BaseModel):
    password: str | None = None


def get_current_user(
    session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI-Dependency: liest das Session-Cookie, validiert Signatur +
    Ablauf, lädt den User, prüft dass die Session nicht durch einen
    Passwort-Reset invalidiert wurde. Wirft 401, wenn irgendwas davon
    fehlschlägt."""
    if session is None:
        raise HTTPException(401, "Not logged in")
    payload = verify_session_token(session)
    if payload is None:
        raise HTTPException(401, "Not logged in")
    user = db.get(User, payload["user_id"])
    if user is None:
        raise HTTPException(401, "Not logged in")
    if user.sessions_invalidated_at is not None:
        issued_at = datetime.fromisoformat(payload["issued_at"])
        if issued_at.tzinfo is None:
            issued_at = issued_at.replace(tzinfo=timezone.utc)
        invalidated_at = user.sessions_invalidated_at
        if invalidated_at.tzinfo is None:
            invalidated_at = invalidated_at.replace(tzinfo=timezone.utc)
        if issued_at < invalidated_at:
            raise HTTPException(401, "Not logged in")
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
        raise HTTPException(401, "Email or password incorrect")
    if user.email_verified_at is None:
        raise HTTPException(403, "Please verify your email address first")

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


@router.patch("/onboarding-complete", response_model=UserOut)
def complete_onboarding(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Markiert den Onboarding-Flow als gesehen (fertig durchlaufen ODER
    übersprungen - beides zählt gleich) - verhindert das automatische
    erneute Auslösen beim nächsten Login. Ein manueller Replay über die
    Account-Seite ruft diesen Endpunkt bewusst NICHT erneut auf, siehe
    Design-Spec "Onboarding-Flow" Abschnitt 2."""
    current_user.onboarding_completed_at = datetime.now(timezone.utc)
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
        # Bewusst NICHT generisch wie forgot-password/resend-verification:
        # beim Signup ist "diese Mail ist schon vergeben" erwartete,
        # marktübliche UX (Nutzer muss wissen, ob registrieren oder
        # einloggen) - das Enumeration-Risiko wiegt hier geringer als bei
        # Passwort-Reset, wo gezieltes Durchprobieren fremder Accounts das
        # eigentliche Bedrohungsmodell ist.
        raise HTTPException(409, "Email address is already registered")

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
def verify_email(
    token: str,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(verify_email_rate_limit),
):
    payload = verify_email_token_signature(token, max_age_seconds=60 * 60 * 24)
    if payload is None or payload.get("purpose") != EmailTokenPurpose.VERIFY_EMAIL.value:
        raise HTTPException(400, "Link is invalid or expired")

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
        raise HTTPException(400, "Link is invalid, expired, or already used")

    user = db.get(User, payload["user_id"])
    already_verified = user.email_verified_at is not None
    user.email_verified_at = datetime.now(timezone.utc)
    token_row.used_at = datetime.now(timezone.utc)
    db.commit()

    if not already_verified:
        try:
            send_welcome_email(to=user.email, display_name=user.display_name)
        except Exception:
            logger.warning("Could not send welcome email", exc_info=True)

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


@router.get("/google/login")
async def google_login(request: Request):
    redirect_uri = settings.google_redirect_uri
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError:
        # z.B. MismatchingStateError - der oauth_state_session-Cookie mit dem
        # ursprünglichen State kam beim Callback nicht (mehr) beim Server an
        # (abgelaufen, Nutzer hat den Login-Versuch doppelt/parallel gestartet,
        # oder eine Browser-Erweiterung/ein Zwischenspeicher hat den Redirect
        # verzögert). Statt eines rohen 500 landet der Nutzer mit einer
        # verständlichen Fehlermeldung zurück auf der Login-Seite und kann es
        # erneut versuchen - Details fürs Debugging gehen ins Server-Log.
        logger.warning("Google OAuth callback failed (state mismatch or expired)", exc_info=True)
        return RedirectResponse(
            url=f"{settings.frontend_base_url.rstrip('/')}/login?error=google_oauth_failed"
        )
    userinfo = token["userinfo"]
    google_sub = userinfo["sub"]
    email = userinfo["email"]
    name = userinfo.get("name") or email

    user = db.query(User).filter(User.google_id == google_sub).first()
    if user is None:
        user = db.query(User).filter(User.email == email).first()
        if user is not None:
            # bestehender E-Mail+Passwort-Account - automatisch verknüpfen.
            # Sicherheitshinweis: War der Account noch NICHT verifiziert,
            # könnte er von einem Angreifer mit der E-Mail-Adresse des
            # Opfers vorregistriert worden sein (Account-Übernahme via
            # gesetztem Passwort, das nie verifiziert wurde). Da Google
            # jetzt als erste Partei den Besitz der E-Mail-Adresse
            # nachweist, wird das gesetzte Passwort ungültig gemacht -
            # der Account wird ab hier reiner Google-Login (analog zum
            # Neu-Signup-Zweig unten).
            if user.email_verified_at is None:
                user.password_hash = None
            user.google_id = google_sub
        else:
            user = create_account(db, email=email, password=None, display_name=name)
            user.google_id = google_sub
            user.privacy_accepted_at = datetime.now(timezone.utc)
        user.email_verified_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)

    session_token = create_session_token(user.id)
    response = RedirectResponse(url=f"{settings.frontend_base_url}/")
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=True,
    )
    return response


@router.post("/forgot-password", status_code=204)
def forgot_password(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(forgot_password_rate_limit),
):
    user = db.query(User).filter(User.email == payload.email).first()
    if user is not None and user.password_hash is not None:
        raw_token = create_email_token(user_id=user.id, purpose=EmailTokenPurpose.RESET_PASSWORD.value)
        db.add(EmailToken(
            user_id=user.id,
            token_hash=hash_email_token(raw_token),
            purpose=EmailTokenPurpose.RESET_PASSWORD,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ))
        db.commit()
        reset_url = f"{settings.frontend_base_url}/reset-password?token={raw_token}"
        send_password_reset_email(to=user.email, reset_url=reset_url)
    # immer 204 - kein Enumeration-Leak, egal ob Account existiert/Passwort hat


@router.post("/reset-password", status_code=204)
def reset_password(
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(reset_password_rate_limit),
):
    token_payload = verify_email_token_signature(payload.token, max_age_seconds=60 * 60)
    if token_payload is None or token_payload.get("purpose") != EmailTokenPurpose.RESET_PASSWORD.value:
        raise HTTPException(400, "Link is invalid or expired")

    token_row = (
        db.query(EmailToken)
        .filter(
            EmailToken.user_id == token_payload["user_id"],
            EmailToken.token_hash == hash_email_token(payload.token),
            EmailToken.purpose == EmailTokenPurpose.RESET_PASSWORD,
            EmailToken.used_at.is_(None),
        )
        .first()
    )
    if token_row is None:
        raise HTTPException(400, "Link is invalid, expired, or already used")

    user = db.get(User, token_payload["user_id"])
    user.password_hash = hash_password(payload.new_password)
    user.sessions_invalidated_at = datetime.now(timezone.utc)
    token_row.used_at = datetime.now(timezone.utc)
    db.commit()


@router.post("/change-password", status_code=204)
def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(change_password_rate_limit),
):
    if current_user.password_hash is None:
        # Google-only-Account - hat kein Passwort zum Ändern. Das Frontend
        # blendet diesen Bereich bereits aus (has_password=false), das
        # hier ist nur die serverseitige Absicherung.
        raise HTTPException(400, "This account has no password set")
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(401, "Current password is incorrect")
    current_user.password_hash = hash_password(payload.new_password)
    # Alle anderen Sessions invalidieren (gekaperte/geleakte Session soll
    # nach Passwortwechsel nicht weiter gültig sein) - aber die aufrufende
    # Session hier direkt erneuern, damit der Browser, der den Wechsel
    # ausgelöst hat, eingeloggt bleibt.
    current_user.sessions_invalidated_at = datetime.now(timezone.utc)
    db.commit()

    token = create_session_token(current_user.id)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=True,
    )


@router.delete("/me", status_code=204)
def delete_account(
    payload: DeleteAccountRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.password_hash is not None:
        if not payload.password or not verify_password(payload.password, current_user.password_hash):
            raise HTTPException(401, "Incorrect password")

    def _log_rmtree_error(func, path, exc_info):
        logger.warning("Konnte %s nicht löschen (Account-Löschung): %s", path, exc_info[1])

    for client_row in current_user.clients:
        for base_dir in (settings.photos_incoming_dir, settings.photos_processed_dir, settings.photos_normalized_dir):
            client_dir = base_dir / str(client_row.id)
            if client_dir.exists():
                shutil.rmtree(client_dir, onerror=_log_rmtree_error)

    # Client/EmailToken werden über ORM-relationship(cascade="all, delete-orphan")
    # entfernt; Pose/DayLog/Photo/AppSetting hängen darunter an DB-seitigen
    # ondelete="CASCADE"-FKs, die "PRAGMA foreign_keys=ON" voraussetzen
    # (siehe app/core/database.py).
    db.delete(current_user)
    db.commit()
    response.delete_cookie(SESSION_COOKIE_NAME, secure=True)


@router.get("/me/export")
def export_my_data(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.models.day_log import DayLog
    from app.models.photo import Photo

    clients_data = []
    for c in current_user.clients:
        day_logs = db.query(DayLog).filter(DayLog.client_id == c.id).all()
        photos = db.query(Photo).filter(Photo.client_id == c.id).all()
        clients_data.append({
            "id": c.id,
            "name": c.name,
            "height_cm": c.height_cm,
            "birth_date": c.birth_date.isoformat() if c.birth_date else None,
            "gender": c.gender,
            "start_date": c.start_date.isoformat() if c.start_date else None,
            "day_logs": [
                {"date": dl.date.isoformat(), "weight_kg": dl.weight_kg, "notes": dl.notes}
                for dl in day_logs
            ],
            "photos": [
                {"filename": p.filename, "taken_at": p.taken_at.isoformat(), "original_path": p.original_path}
                for p in photos
            ],
        })

    return {
        "email": current_user.email,
        "display_name": current_user.display_name,
        "account_type": current_user.account_type.value,
        "created_at": current_user.created_at.isoformat(),
        "clients": clients_data,
    }
