from datetime import datetime, timezone

from app.models.user import AccountType, User
from app.services.auth import hash_password


def _login(client, db_session, email="a@b.com", password="pw12345", account_type=AccountType.COACH):
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name="A",
        email_verified_at=datetime.now(timezone.utc),
        account_type=account_type,
    )
    db_session.add(user)
    db_session.commit()
    client.post("/api/auth/login", json={"email": email, "password": password})
    return user


def test_checkout_creates_stripe_customer_and_session(client, db_session, monkeypatch):
    created_customers = []
    created_sessions = []

    class FakeCustomer:
        id = "cus_fake123"

    class FakeSession:
        url = "https://checkout.stripe.com/fake-session"

    monkeypatch.setattr(
        "app.routers.billing.stripe.Customer.create",
        lambda **kwargs: created_customers.append(kwargs) or FakeCustomer(),
    )
    monkeypatch.setattr(
        "app.routers.billing.stripe.checkout.Session.create",
        lambda **kwargs: created_sessions.append(kwargs) or FakeSession(),
    )

    _login(client, db_session, account_type=AccountType.COACH)
    response = client.post("/api/billing/checkout", json={"tier": "starter"})

    assert response.status_code == 200
    assert response.json()["checkout_url"] == "https://checkout.stripe.com/fake-session"
    assert created_customers[0]["email"] == "a@b.com"
    assert created_sessions[0]["subscription_data"] == {"trial_period_days": 14}


def test_checkout_reuses_existing_stripe_customer(client, db_session, monkeypatch):
    monkeypatch.setattr(
        "app.routers.billing.stripe.checkout.Session.create",
        lambda **kwargs: type("S", (), {"url": "https://checkout.stripe.com/fake"})(),
    )

    def _fail_if_called(**kwargs):
        raise AssertionError("Customer.create sollte nicht erneut aufgerufen werden")

    monkeypatch.setattr("app.routers.billing.stripe.Customer.create", _fail_if_called)

    user = _login(client, db_session, account_type=AccountType.COACH)
    user.stripe_customer_id = "cus_existing"
    db_session.commit()

    response = client.post("/api/billing/checkout", json={"tier": "starter"})
    assert response.status_code == 200


def test_checkout_single_account_cannot_choose_coach_tier(client, db_session):
    _login(client, db_session, account_type=AccountType.SINGLE)
    response = client.post("/api/billing/checkout", json={"tier": "starter"})
    assert response.status_code == 400


def test_checkout_coach_cannot_choose_single_tier(client, db_session):
    _login(client, db_session, account_type=AccountType.COACH)
    response = client.post("/api/billing/checkout", json={"tier": "single"})
    assert response.status_code == 400


def test_checkout_single_account_gets_no_trial(client, db_session, monkeypatch):
    created_sessions = []
    monkeypatch.setattr(
        "app.routers.billing.stripe.Customer.create",
        lambda **kwargs: type("C", (), {"id": "cus_fake"})(),
    )
    monkeypatch.setattr(
        "app.routers.billing.stripe.checkout.Session.create",
        lambda **kwargs: created_sessions.append(kwargs) or type("S", (), {"url": "https://x"})(),
    )

    _login(client, db_session, account_type=AccountType.SINGLE)
    client.post("/api/billing/checkout", json={"tier": "single"})

    assert "subscription_data" not in created_sessions[0]


def test_portal_requires_existing_stripe_customer(client, db_session):
    _login(client, db_session)
    response = client.post("/api/billing/portal")
    assert response.status_code == 400


def test_portal_returns_url_for_existing_customer(client, db_session, monkeypatch):
    monkeypatch.setattr(
        "app.routers.billing.stripe.billing_portal.Session.create",
        lambda **kwargs: type("P", (), {"url": "https://billing.stripe.com/fake-portal"})(),
    )
    user = _login(client, db_session)
    user.stripe_customer_id = "cus_existing"
    db_session.commit()

    response = client.post("/api/billing/portal")
    assert response.status_code == 200
    assert response.json()["portal_url"] == "https://billing.stripe.com/fake-portal"
