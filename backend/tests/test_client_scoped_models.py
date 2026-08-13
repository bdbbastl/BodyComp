from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.client import Client
from app.models.day_log import DayLog
from app.models.pose import Pose
from app.models.user import User


def _make_two_clients(db_session):
    user = User(email="a@b.com", password_hash="x", display_name="A")
    db_session.add(user)
    db_session.flush()
    client_a = Client(owner_id=user.id, name="Kunde A")
    client_b = Client(owner_id=user.id, name="Kunde B")
    db_session.add_all([client_a, client_b])
    db_session.commit()
    return client_a, client_b


def test_two_clients_can_have_same_pose_name(db_session):
    client_a, client_b = _make_two_clients(db_session)
    db_session.add(Pose(client_id=client_a.id, name="Front Double Biceps", sort_order=0))
    db_session.add(Pose(client_id=client_b.id, name="Front Double Biceps", sort_order=0))
    db_session.commit()  # darf NICHT scheitern

    assert db_session.query(Pose).count() == 2


def test_same_client_cannot_have_duplicate_pose_name(db_session):
    client_a, _ = _make_two_clients(db_session)
    db_session.add(Pose(client_id=client_a.id, name="Front Double Biceps", sort_order=0))
    db_session.commit()

    db_session.add(Pose(client_id=client_a.id, name="Front Double Biceps", sort_order=1))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_two_clients_can_have_daylog_same_date(db_session):
    client_a, client_b = _make_two_clients(db_session)
    db_session.add(DayLog(client_id=client_a.id, date=date(2026, 1, 1), weight_kg=80))
    db_session.add(DayLog(client_id=client_b.id, date=date(2026, 1, 1), weight_kg=90))
    db_session.commit()  # darf NICHT scheitern

    assert db_session.query(DayLog).count() == 2


def test_same_client_cannot_have_duplicate_daylog_date(db_session):
    client_a, _ = _make_two_clients(db_session)
    db_session.add(DayLog(client_id=client_a.id, date=date(2026, 1, 1), weight_kg=80))
    db_session.commit()

    db_session.add(DayLog(client_id=client_a.id, date=date(2026, 1, 1), weight_kg=81))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
