from app.services.auth import hash_password, verify_password


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
