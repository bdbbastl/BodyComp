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


def test_webhook_updates_subscription_status_on_update_event(client, db_session, monkeypatch):
    from datetime import datetime, timezone

    user = User(
        email="webhook@b.com", password_hash=hash_password("pw12345"), display_name="W",
        email_verified_at=datetime.now(timezone.utc), stripe_customer_id="cus_webhook_test",
    )
    db_session.add(user)
    db_session.commit()

    fake_event = {
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "customer": "cus_webhook_test",
                "status": "active",
                "items": {"data": [{"price": {"id": "price_starter_fake"}}]},
                "trial_end": None,
            }
        },
    }
    monkeypatch.setattr("app.routers.billing.TIER_PRICE_IDS", {"starter": "price_starter_fake"})
    monkeypatch.setattr(
        "app.routers.billing.stripe.Webhook.construct_event", lambda *a, **kw: fake_event
    )

    response = client.post(
        "/api/billing/webhook", content=b"{}", headers={"stripe-signature": "fake"}
    )
    assert response.status_code == 204

    db_session.refresh(user)
    assert user.subscription_status == "active"
    assert user.subscription_tier == "starter"


def test_webhook_marks_canceled_on_deletion_event(client, db_session, monkeypatch):
    from datetime import datetime, timezone

    user = User(
        email="webhook2@b.com", password_hash=hash_password("pw12345"), display_name="W2",
        email_verified_at=datetime.now(timezone.utc), stripe_customer_id="cus_webhook_test2",
        subscription_status="active",
    )
    db_session.add(user)
    db_session.commit()

    fake_event = {
        "type": "customer.subscription.deleted",
        "data": {"object": {"customer": "cus_webhook_test2"}},
    }
    monkeypatch.setattr(
        "app.routers.billing.stripe.Webhook.construct_event", lambda *a, **kw: fake_event
    )

    response = client.post(
        "/api/billing/webhook", content=b"{}", headers={"stripe-signature": "fake"}
    )
    assert response.status_code == 204

    db_session.refresh(user)
    assert user.subscription_status == "canceled"


class _FakeStripeObject(dict):
    """Ahmt das echte Verhalten von stripe._stripe_object.StripeObject nach:
    []/`in` funktionieren (dict-Basis), aber .get() NICHT - das echte SDK
    ueberschreibt __getattr__ so, dass .get() zu einem KeyError/AttributeError
    fuehrt statt zur eingebauten dict.get()-Methode (gefunden im Live-Debugging
    am 2026-08-17: echte Webhooks crashten mit `AttributeError: get` in
    routers/billing.py, weil die Tests bisher nur mit reinen dicts liefen,
    deren .get() klaglos funktioniert und den Bug nie aufgedeckt hat)."""

    def get(self, *args, **kwargs):
        raise AttributeError("get")


def test_webhook_handles_real_stripe_object_without_get_method(client, db_session, monkeypatch):
    """Regression fuer den Live-Bug: obj.get("trial_end") crasht mit dem
    echten Stripe-SDK-Objekttyp - der Code muss stattdessen []/try-except
    verwenden (siehe Fix in routers/billing.py)."""
    user = User(
        email="webhook3@b.com", password_hash=hash_password("pw12345"), display_name="W3",
        email_verified_at=datetime.now(timezone.utc), stripe_customer_id="cus_webhook_test3",
    )
    db_session.add(user)
    db_session.commit()

    trial_end_ts = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp())
    fake_event = {
        "type": "customer.subscription.created",
        "data": {
            "object": _FakeStripeObject(
                customer="cus_webhook_test3",
                status="trialing",
                items={"data": [{"price": {"id": "price_starter_fake"}}]},
                trial_end=trial_end_ts,
            )
        },
    }
    monkeypatch.setattr("app.routers.billing.TIER_PRICE_IDS", {"starter": "price_starter_fake"})
    monkeypatch.setattr(
        "app.routers.billing.stripe.Webhook.construct_event", lambda *a, **kw: fake_event
    )

    response = client.post(
        "/api/billing/webhook", content=b"{}", headers={"stripe-signature": "fake"}
    )
    assert response.status_code == 204

    db_session.refresh(user)
    assert user.subscription_status == "trialing"
    assert user.subscription_tier == "starter"
    assert user.trial_ends_at.replace(tzinfo=timezone.utc) == datetime(2026, 9, 1, tzinfo=timezone.utc)


def test_webhook_rejects_invalid_signature(client, db_session, monkeypatch):
    import stripe as stripe_module

    def _raise(*a, **kw):
        raise stripe_module.error.SignatureVerificationError("bad sig", "sig_header")

    monkeypatch.setattr("app.routers.billing.stripe.Webhook.construct_event", _raise)

    response = client.post(
        "/api/billing/webhook", content=b"{}", headers={"stripe-signature": "bad"}
    )
    assert response.status_code == 400


def test_webhook_ignores_events_for_unknown_customer(client, db_session, monkeypatch):
    fake_event = {
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "customer": "cus_does_not_exist",
                "status": "active",
                "items": {"data": [{"price": {"id": "price_starter_fake"}}]},
                "trial_end": None,
            }
        },
    }
    monkeypatch.setattr(
        "app.routers.billing.stripe.Webhook.construct_event", lambda *a, **kw: fake_event
    )

    response = client.post(
        "/api/billing/webhook", content=b"{}", headers={"stripe-signature": "fake"}
    )
    assert response.status_code == 204  # kein Fehler, nur nichts zu tun
