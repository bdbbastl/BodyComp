"""
Passwort-Hashing für die Account-Authentifizierung. bcrypt statt eines
selbstgebauten Hashings, weil bcrypt Salting und einen konfigurierbaren
Work-Factor eingebaut hat - der Industriestandard für Passwort-Hashes.
"""
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
    return _serializer.dumps({"user_id": user_id})


def verify_session_token(token: str) -> int | None:
    """Gibt die user_id zurück, wenn die Signatur gültig und das Cookie
    nicht abgelaufen ist - sonst None (nie eine Exception nach außen)."""
    try:
        data = _serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
    except BadSignature:
        return None
    return data.get("user_id")
