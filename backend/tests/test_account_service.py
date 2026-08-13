from app.models.client import Client
from app.models.user import AccountType, User
from app.services.account import create_account


def test_create_account_creates_one_implicit_client(db_session):
    user = create_account(
        db_session,
        email="basti@example.com",
        password="Grindcore123!",
        display_name="Basti",
        account_type=AccountType.COACH,
    )

    assert user.id is not None
    clients = db_session.query(Client).filter(Client.owner_id == user.id).all()
    assert len(clients) == 1
    assert clients[0].name == "Basti"


def test_create_account_hashes_password(db_session):
    user = create_account(
        db_session,
        email="basti@example.com",
        password="Grindcore123!",
        display_name="Basti",
        account_type=AccountType.SINGLE,
    )
    assert user.password_hash != "Grindcore123!"
