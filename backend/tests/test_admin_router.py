from datetime import date, datetime, timedelta, timezone

from app.models.checkin_submission import CheckinStatus, CheckinSubmission
from app.models.client import Client
from app.models.day_log import DayLog
from app.models.photo import Photo, ProcessingStatus
from app.models.user import User
from app.services.auth import SESSION_COOKIE_NAME, create_session_token, hash_password


def _make_user(db_session, email="user@example.com", is_admin=False, account_type=None, created_at=None):
    from app.models.user import AccountType

    user = User(
        email=email,
        password_hash=hash_password("Grindcore123!"),
        display_name="Test User",
        email_verified_at=datetime.now(timezone.utc),
        is_admin=is_admin,
        account_type=account_type or AccountType.SINGLE,
    )
    if created_at is not None:
        user.created_at = created_at
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _login_as(client, user):
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)


def test_admin_routes_reject_non_admin(client, db_session):
    user = _make_user(db_session, is_admin=False)
    _login_as(client, user)

    assert client.get("/api/admin/overview").status_code == 403
    assert client.get("/api/admin/accounts").status_code == 403
    assert client.get(f"/api/admin/accounts/{user.id}").status_code == 403
    assert client.patch(f"/api/admin/accounts/{user.id}", json={"is_active": False}).status_code == 403


def test_admin_routes_reject_anonymous(client, db_session):
    assert client.get("/api/admin/overview").status_code == 401


def test_overview_counts_accounts(client, db_session):
    from app.models.user import AccountType

    admin = _make_user(db_session, email="admin@example.com", is_admin=True)
    _make_user(db_session, email="single@example.com", account_type=AccountType.SINGLE)
    _make_user(db_session, email="coach@example.com", account_type=AccountType.COACH)
    _login_as(client, admin)

    response = client.get("/api/admin/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["total_accounts"] == 3
    assert body["single_accounts"] == 2  # admin selbst ist auch SINGLE per Default
    assert body["coach_accounts"] == 1


def test_accounts_list_includes_client_count_and_activity_status(client, db_session):
    admin = _make_user(db_session, email="admin@example.com", is_admin=True)
    active_user = _make_user(db_session, email="active@example.com")
    inactive_user = _make_user(db_session, email="inactive@example.com")
    never_user = _make_user(db_session, email="never@example.com")
    _login_as(client, admin)

    active_client = Client(owner_id=active_user.id, name="Active Client")
    db_session.add(active_client)
    inactive_client = Client(owner_id=inactive_user.id, name="Inactive Client")
    db_session.add(inactive_client)
    never_client = Client(owner_id=never_user.id, name="Never Client")
    db_session.add(never_client)
    db_session.commit()

    db_session.add(DayLog(client_id=active_client.id, date=date.today()))
    db_session.add(
        DayLog(client_id=inactive_client.id, date=date.today() - timedelta(days=30))
    )
    db_session.commit()

    response = client.get("/api/admin/accounts")
    assert response.status_code == 200
    by_email = {row["email"]: row for row in response.json()}

    assert by_email["active@example.com"]["client_count"] == 1
    assert by_email["active@example.com"]["activity_status"] == "active"
    assert by_email["inactive@example.com"]["activity_status"] == "inactive"
    assert by_email["never@example.com"]["activity_status"] == "never"
    assert by_email["never@example.com"]["last_activity_at"] is None


def test_accounts_list_handles_naive_and_aware_timestamps_together(client, db_session):
    """Regressionstest für einen Produktionsfehler: Postgres liefert
    Photo.taken_at/CheckinSubmission.submitted_at ohne tzinfo zurück,
    während der DayLog-Zweig in _last_activity_for_client_ids selbst
    tz-aware Werte baut - der Vergleich der beiden crashte mit
    "can't compare offset-naive and offset-aware datetimes", sobald ein
    Client sowohl einen DayLog- als auch einen Photo-Eintrag hatte. Auf
    SQLite fiel das in den bisherigen Tests nicht auf, weil kein Test
    einen Client mit BEIDEN Quellen gleichzeitig hatte."""
    admin = _make_user(db_session, email="admin@example.com", is_admin=True)
    target_user = _make_user(db_session, email="target@example.com")
    _login_as(client, admin)

    target_client = Client(owner_id=target_user.id, name="Target Client")
    db_session.add(target_client)
    db_session.commit()

    # DayLog macht den Vergleichswert tz-aware (siehe _last_activity_for_client_ids).
    db_session.add(DayLog(client_id=target_client.id, date=date.today()))
    # Photo absichtlich mit einem NAIVEN Zeitstempel - genau das Verhalten,
    # das Postgres in Produktion für DateTime-Spalten ohne timezone=True liefert.
    db_session.add(
        Photo(
            client_id=target_client.id,
            filename="p1.jpg",
            original_path=f"photos_processed/{target_client.id}/p1.jpg",
            taken_at=datetime(2026, 1, 1, 12, 0, 0),  # bewusst ohne tzinfo
            status=ProcessingStatus.PROCESSED,
        )
    )
    db_session.commit()

    response = client.get("/api/admin/accounts")
    assert response.status_code == 200
    by_email = {row["email"]: row for row in response.json()}
    assert by_email["target@example.com"]["activity_status"] == "active"


def test_account_detail_includes_clients(client, db_session):
    admin = _make_user(db_session, email="admin@example.com", is_admin=True)
    target = _make_user(db_session, email="target@example.com")
    _login_as(client, admin)

    c = Client(owner_id=target.id, name="Client A")
    db_session.add(c)
    db_session.commit()
    db_session.add(
        Photo(
            client_id=c.id,
            filename="p1.jpg",
            original_path=f"photos_processed/{c.id}/p1.jpg",
            taken_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            status=ProcessingStatus.PROCESSED,
        )
    )
    db_session.commit()

    response = client.get(f"/api/admin/accounts/{target.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "target@example.com"
    assert len(body["clients"]) == 1
    assert body["clients"][0]["name"] == "Client A"
    assert body["clients"][0]["photo_count"] == 1


def test_account_detail_404_for_unknown_id(client, db_session):
    admin = _make_user(db_session, email="admin@example.com", is_admin=True)
    _login_as(client, admin)

    response = client.get("/api/admin/accounts/999999")
    assert response.status_code == 404


def test_deactivate_and_reactivate_account(client, db_session):
    admin = _make_user(db_session, email="admin@example.com", is_admin=True)
    target = _make_user(db_session, email="target@example.com")
    _login_as(client, admin)

    response = client.patch(f"/api/admin/accounts/{target.id}", json={"is_active": False})
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    response = client.patch(f"/api/admin/accounts/{target.id}", json={"is_active": True})
    assert response.status_code == 200
    assert response.json()["is_active"] is True


def test_admin_cannot_deactivate_own_account(client, db_session):
    admin = _make_user(db_session, email="admin@example.com", is_admin=True)
    _login_as(client, admin)

    response = client.patch(f"/api/admin/accounts/{admin.id}", json={"is_active": False})
    assert response.status_code == 400


def test_deactivate_404_for_unknown_id(client, db_session):
    admin = _make_user(db_session, email="admin@example.com", is_admin=True)
    _login_as(client, admin)

    response = client.patch("/api/admin/accounts/999999", json={"is_active": False})
    assert response.status_code == 404


def test_account_detail_includes_total_checkins(client, db_session):
    from app.models.client import Client
    from app.models.checkin_submission import CheckinStatus, CheckinSubmission

    admin = _make_user(db_session, email="admin2@example.com", is_admin=True)
    target = _make_user(db_session, email="target-checkins@example.com")
    _login_as(client, admin)

    c1 = Client(owner_id=target.id, name="C1")
    db_session.add(c1)
    db_session.commit()
    db_session.refresh(c1)

    db_session.add_all(
        [
            CheckinSubmission(client_id=c1.id, weight_kg=80.0, status=CheckinStatus.PENDING),
            CheckinSubmission(client_id=c1.id, weight_kg=81.0, status=CheckinStatus.REVIEWED),
        ]
    )
    db_session.commit()

    response = client.get(f"/api/admin/accounts/{target.id}")
    assert response.status_code == 200
    assert response.json()["total_checkins"] == 2


def test_account_detail_sums_known_photo_sizes_and_counts_unknown(client, db_session):
    from app.models.client import Client
    from app.models.photo import Photo, ProcessingStatus
    from datetime import datetime, timezone

    admin = _make_user(db_session, email="admin3@example.com", is_admin=True)
    target = _make_user(db_session, email="target-storage@example.com")
    _login_as(client, admin)

    c1 = Client(owner_id=target.id, name="C1")
    db_session.add(c1)
    db_session.commit()
    db_session.refresh(c1)

    db_session.add_all(
        [
            Photo(
                client_id=c1.id,
                filename="a.jpg",
                original_path=f"photos_processed/{c1.id}/a.jpg",
                taken_at=datetime.now(timezone.utc),
                status=ProcessingStatus.PROCESSED,
                file_size_bytes=1000,
            ),
            Photo(
                client_id=c1.id,
                filename="b.jpg",
                original_path=f"photos_processed/{c1.id}/b.jpg",
                taken_at=datetime.now(timezone.utc),
                status=ProcessingStatus.PROCESSED,
                file_size_bytes=2000,
            ),
            Photo(
                client_id=c1.id,
                filename="c.jpg",
                original_path=f"photos_processed/{c1.id}/c.jpg",
                taken_at=datetime.now(timezone.utc),
                status=ProcessingStatus.PROCESSED,
                file_size_bytes=None,
            ),
        ]
    )
    db_session.commit()

    response = client.get(f"/api/admin/accounts/{target.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["total_storage_bytes"] == 3000
    assert body["photos_with_unknown_size"] == 1


def test_billing_returns_empty_state_when_no_stripe_customer(client, db_session):
    admin = _make_user(db_session, email="admin4@example.com", is_admin=True)
    target = _make_user(db_session, email="target-no-stripe@example.com")
    _login_as(client, admin)

    response = client.get(f"/api/admin/accounts/{target.id}/billing")
    assert response.status_code == 200
    body = response.json()
    assert body["has_stripe_customer"] is False
    assert body["subscription_id"] is None
    assert body["recent_invoices"] == []


def test_billing_fetches_live_stripe_data(client, db_session, monkeypatch):
    admin = _make_user(db_session, email="admin5@example.com", is_admin=True)
    target = _make_user(db_session, email="target-stripe@example.com")
    target.stripe_customer_id = "cus_test123"
    db_session.commit()
    _login_as(client, admin)

    fake_subscription = {
        "data": [
            {"id": "sub_abc", "current_period_end": 1893456000}  # 2030-01-01 UTC
        ]
    }
    fake_invoices = {
        "data": [
            {
                "amount_paid": 4900,
                "currency": "eur",
                "status_transitions": {"paid_at": 1735689600},  # 2025-01-01 UTC
                "status": "paid",
            }
        ]
    }

    monkeypatch.setattr(
        "app.routers.admin.stripe.Subscription.list", lambda **kwargs: fake_subscription
    )
    monkeypatch.setattr("app.routers.admin.stripe.Invoice.list", lambda **kwargs: fake_invoices)

    response = client.get(f"/api/admin/accounts/{target.id}/billing")
    assert response.status_code == 200
    body = response.json()
    assert body["has_stripe_customer"] is True
    assert body["subscription_id"] == "sub_abc"
    assert len(body["recent_invoices"]) == 1
    assert body["recent_invoices"][0]["amount"] == 49.0
    assert body["recent_invoices"][0]["currency"] == "eur"


def test_billing_handles_stripe_error_gracefully(client, db_session, monkeypatch):
    admin = _make_user(db_session, email="admin6@example.com", is_admin=True)
    target = _make_user(db_session, email="target-stripe-err@example.com")
    target.stripe_customer_id = "cus_broken"
    db_session.commit()
    _login_as(client, admin)

    def _raise(**kwargs):
        raise Exception("Stripe network error")

    monkeypatch.setattr("app.routers.admin.stripe.Subscription.list", _raise)

    response = client.get(f"/api/admin/accounts/{target.id}/billing")
    assert response.status_code == 200
    body = response.json()
    assert body["has_stripe_customer"] is True
    assert body["subscription_id"] is None
    assert body["recent_invoices"] == []


def test_overview_includes_signups_per_week(client, db_session):
    admin = _make_user(db_session, email="admin7@example.com", is_admin=True)
    _login_as(client, admin)

    response = client.get("/api/admin/overview")
    assert response.status_code == 200
    weeks = response.json()["signups_per_week"]
    assert len(weeks) == 12
    # admin selbst wurde gerade erst angelegt -> aktuelle Woche hat mind. 1
    assert weeks[-1]["count"] >= 1
