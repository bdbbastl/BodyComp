from app.models.client import Client
from app.models.user import User


def test_client_belongs_to_user(db_session):
    user = User(email="a@b.com", password_hash="x", display_name="A")
    db_session.add(user)
    db_session.flush()

    client_row = Client(owner_id=user.id, name="Mein Profil")
    db_session.add(client_row)
    db_session.commit()

    assert client_row.id is not None
    assert user.clients[0].name == "Mein Profil"


def test_client_deleted_when_owner_deleted(db_session):
    user = User(email="a@b.com", password_hash="x", display_name="A")
    db_session.add(user)
    db_session.flush()
    db_session.add(Client(owner_id=user.id, name="Mein Profil"))
    db_session.commit()

    db_session.delete(user)
    db_session.commit()

    assert db_session.query(Client).count() == 0
