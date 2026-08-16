from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.models.client import Client
from app.models.user import AccountType, User
from app.services.auth import hash_password
from app.services.billing import (
    EXEMPT_EMAILS,
    FREE_CHECKINS_LIMIT,
    check_and_consume_free_checkin,
    check_can_create_client,
    client_limit_for,
    has_active_subscription,
    is_billing_exempt,
)


def _make_user(db_session, **kwargs) -> User:
    defaults = dict(
        email="a@b.com",
        password_hash=hash_password("pw12345"),
        display_name="A",
        email_verified_at=datetime.now(timezone.utc),
        account_type=AccountType.COACH,
    )
    defaults.update(kwargs)
    user = User(**defaults)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_is_billing_exempt_matches_hardcoded_allowlist(db_session):
    exempt_user = _make_user(db_session, email=next(iter(EXEMPT_EMAILS)))
    normal_user = _make_user(db_session, email="someone-else@example.com")
    assert is_billing_exempt(exempt_user) is True
    assert is_billing_exempt(normal_user) is False


def test_has_active_subscription_true_for_trialing_and_active(db_session):
    trialing = _make_user(db_session, email="t@b.com", subscription_status="trialing")
    active = _make_user(db_session, email="ac@b.com", subscription_status="active")
    none_status = _make_user(db_session, email="n@b.com", subscription_status=None)
    past_due = _make_user(db_session, email="p@b.com", subscription_status="past_due")
    assert has_active_subscription(trialing) is True
    assert has_active_subscription(active) is True
    assert has_active_subscription(none_status) is False
    assert has_active_subscription(past_due) is False


def test_client_limit_for_matches_tier(db_session):
    starter = _make_user(db_session, email="s@b.com", subscription_status="active", subscription_tier="starter")
    pro = _make_user(db_session, email="pr@b.com", subscription_status="active", subscription_tier="pro")
    business = _make_user(db_session, email="bu@b.com", subscription_status="active", subscription_tier="business")
    unsubscribed = _make_user(db_session, email="u@b.com")
    assert client_limit_for(starter) == 5
    assert client_limit_for(pro) == 20
    assert client_limit_for(business) is None  # unbegrenzt
    assert client_limit_for(unsubscribed) == 1  # nur der automatisch angelegte Client


def test_check_can_create_client_raises_402_when_over_limit(db_session):
    user = _make_user(db_session, email="over@b.com", subscription_status="active", subscription_tier="starter")
    for i in range(5):
        db_session.add(Client(owner_id=user.id, name=f"Client {i}"))
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        check_can_create_client(user, db_session)
    assert exc_info.value.status_code == 402


def test_check_can_create_client_allows_when_under_limit(db_session):
    user = _make_user(db_session, email="under@b.com", subscription_status="active", subscription_tier="starter")
    db_session.add(Client(owner_id=user.id, name="Client 1"))
    db_session.commit()

    check_can_create_client(user, db_session)  # darf nicht werfen


def test_check_can_create_client_exempt_user_never_blocked(db_session):
    user = _make_user(db_session, email=next(iter(EXEMPT_EMAILS)))
    for i in range(50):
        db_session.add(Client(owner_id=user.id, name=f"Client {i}"))
    db_session.commit()

    check_can_create_client(user, db_session)  # darf nicht werfen, egal wie viele Clients


def test_check_and_consume_free_checkin_increments_counter(db_session):
    user = _make_user(db_session, email="single@b.com", account_type=AccountType.SINGLE)
    assert user.free_checkins_used == 0

    check_and_consume_free_checkin(user)
    assert user.free_checkins_used == 1

    check_and_consume_free_checkin(user)
    assert user.free_checkins_used == 2


def test_check_and_consume_free_checkin_raises_402_when_exhausted(db_session):
    user = _make_user(
        db_session, email="exhausted@b.com", account_type=AccountType.SINGLE,
        free_checkins_used=FREE_CHECKINS_LIMIT,
    )
    with pytest.raises(HTTPException) as exc_info:
        check_and_consume_free_checkin(user)
    assert exc_info.value.status_code == 402
    assert user.free_checkins_used == FREE_CHECKINS_LIMIT  # nicht weiter hochgezählt


def test_check_and_consume_free_checkin_noop_for_coach_accounts(db_session):
    coach = _make_user(db_session, email="coach@b.com", account_type=AccountType.COACH)
    check_and_consume_free_checkin(coach)  # darf nicht werfen
    assert coach.free_checkins_used == 0  # Coaches werden nicht über Check-ins limitiert


def test_check_and_consume_free_checkin_noop_with_active_subscription(db_session):
    user = _make_user(
        db_session, email="paid@b.com", account_type=AccountType.SINGLE,
        subscription_status="active", subscription_tier="single",
        free_checkins_used=FREE_CHECKINS_LIMIT,
    )
    check_and_consume_free_checkin(user)  # darf nicht werfen, zahlendes Abo
    assert user.free_checkins_used == FREE_CHECKINS_LIMIT  # kein weiteres Hochzählen nötig
