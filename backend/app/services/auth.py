"""
Passwort-Hashing für die Account-Authentifizierung. bcrypt statt eines
selbstgebauten Hashings, weil bcrypt Salting und einen konfigurierbaren
Work-Factor eingebaut hat - der Industriestandard für Passwort-Hashes.
"""
import hashlib
from datetime import datetime, timezone

import bcrypt
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.core.config import settings


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))


SESSION_COOKIE_NAME = "session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30  # 30 Tage

_serializer = URLSafeTimedSerializer(settings.session_secret_key, salt="session-cookie")


def create_session_token(user_id: int) -> str:
    return _serializer.dumps({"user_id": user_id, "issued_at": datetime.now(timezone.utc).isoformat()})


def verify_session_token(token: str) -> dict | None:
    """Gibt das Token-Payload (user_id, issued_at) zurück, wenn die
    Signatur gültig und das Cookie nicht abgelaufen ist - sonst None
    (nie eine Exception nach außen)."""
    try:
        return _serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
    except BadSignature:
        return None


_email_token_serializer = URLSafeTimedSerializer(settings.session_secret_key, salt="email-token")


def create_email_token(*, user_id: int, purpose: str) -> str:
    """Erzeugt einen signierten Token für E-Mail-Bestätigung/Passwort-
    Reset-Links. Der Aufrufer speichert `hash_email_token(token)` in der
    DB (siehe EmailToken.token_hash), NICHT den Token selbst."""
    return _email_token_serializer.dumps({"user_id": user_id, "purpose": purpose})


def verify_email_token_signature(token: str, *, max_age_seconds: int) -> dict | None:
    """Prüft nur Signatur + Ablauf des itsdangerous-Tokens - sagt NICHTS
    darüber aus, ob der zugehörige EmailToken in der DB noch existiert
    oder schon benutzt wurde (das prüft der Aufrufer separat gegen
    token_hash/used_at)."""
    try:
        return _email_token_serializer.loads(token, max_age=max_age_seconds)
    except BadSignature:
        return None


def hash_email_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
