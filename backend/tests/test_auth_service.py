from app import services
from app.services.auth import (
    create_email_token,
    create_session_token,
    hash_email_token,
    hash_password,
    verify_email_token_signature,
    verify_password,
    verify_session_token,
)


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


def test_create_email_token_is_verifiable():
    token = create_email_token(user_id=42, purpose="verify_email")
    payload = verify_email_token_signature(token, max_age_seconds=3600)
    assert payload == {"user_id": 42, "purpose": "verify_email"}


def test_verify_email_token_signature_rejects_tampered_token():
    token = create_email_token(user_id=42, purpose="verify_email")
    # Nicht das letzte Zeichen kippen: bei Base64url-Padding kann ein
    # geänderter letzter Zeichen manchmal auf dieselben Bytes dekodieren
    # (ungenutzte Padding-Bits), was den Test nichtdeterministisch macht.
    # Stattdessen ein Zeichen weiter vorne im Payload-Segment kippen.
    tampered = token[:-8] + ("X" if token[-8] != "X" else "Y") + token[-7:]
    assert verify_email_token_signature(tampered, max_age_seconds=3600) is None


def test_verify_email_token_signature_rejects_expired_token():
    token = create_email_token(user_id=42, purpose="verify_email")
    assert verify_email_token_signature(token, max_age_seconds=-1) is None


def test_hash_email_token_is_deterministic_and_not_reversible():
    token = "some-raw-token-value"
    h1 = hash_email_token(token)
    h2 = hash_email_token(token)
    assert h1 == h2
    assert h1 != token
    assert len(h1) == 64  # sha256 hex digest
