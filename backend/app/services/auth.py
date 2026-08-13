"""
Passwort-Hashing für die Account-Authentifizierung. bcrypt statt eines
selbstgebauten Hashings, weil bcrypt Salting und einen konfigurierbaren
Work-Factor eingebaut hat - der Industriestandard für Passwort-Hashes.
"""
import bcrypt


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
