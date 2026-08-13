from app import services
from app.services.auth import create_session_token, hash_password, verify_password, verify_session_token


def test_hash_password_is_not_plaintext():
    hashed = hash_password("Grindcore123!")
    assert hashed != "Grindcore123!"
    assert hashed.startswith("$2b$")


def test_verify_password_correct():
    hashed = hash_password("Grindcore123!")
    assert verify_password("Grindcore123!", hashed) is True


def test_verify_password_wrong():
    hashed = hash_password("Grindcore123!")
    assert verify_password("wrong-password", hashed) is False


def test_verify_session_token_rejects_expired_token(monkeypatch):
    token = create_session_token(user_id=1)
    # Erzwingt, dass jedes Token als abgelaufen gilt, ohne echte Zeit
    # verstreichen zu lassen.
    monkeypatch.setattr(services.auth, "SESSION_MAX_AGE_SECONDS", -1)
    assert verify_session_token(token) is None
