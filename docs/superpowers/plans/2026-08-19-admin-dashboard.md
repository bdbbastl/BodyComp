# Master-Admin-Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the app operator a standalone `/admin` area showing account overview stats and a per-account activity/subscription table, with the ability to deactivate/reactivate an account.

**Architecture:** Two new boolean columns on `User` (`is_admin`, `is_active`), a `require_admin` FastAPI dependency, a new read-mostly `admin` router/schema pair on the backend, and a standalone (non-`ClientShell`) `/admin` route pair on the frontend guarded client-side by `is_admin` and server-side by `require_admin` on every call.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic, React, TypeScript, TanStack Query.

---

### Task 1: `User` model fields + migration + `UserOut.is_admin` + `require_admin` dependency

**Files:**
- Modify: `backend/app/models/user.py`
- Create: `backend/alembic/versions/0005_admin_fields.py`
- Modify: `backend/app/schemas/auth.py`
- Modify: `backend/app/routers/auth.py`
- Test: `backend/tests/test_auth_router.py`

- [ ] **Step 1: Write the failing test for `require_admin`**

Add to `backend/tests/test_auth_router.py`:

```python
def test_me_includes_is_admin_field(client, db_session):
    user = _make_user(db_session)
    _login_as(client, user)
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json()["is_admin"] is False


def test_require_admin_rejects_non_admin(client, db_session):
    from app.routers.auth import require_admin

    user = _make_user(db_session)
    _login_as(client, user)

    with pytest.raises(HTTPException) as exc_info:
        require_admin(user=user)
    assert exc_info.value.status_code == 403


def test_require_admin_allows_admin(db_session):
    from app.routers.auth import require_admin

    user = _make_user(db_session, email="admin@example.com")
    user.is_admin = True
    db_session.commit()

    result = require_admin(user=user)
    assert result is user
```

Add these imports at the top of `backend/tests/test_auth_router.py` if not already present:

```python
import pytest
from fastapi import HTTPException
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_auth_router.py -k "is_admin or require_admin" -v`
Expected: FAIL (`is_admin` doesn't exist on `User`/`UserOut`, `require_admin` doesn't exist in `app.routers.auth`).

- [ ] **Step 3: Add the columns to `User`**

In `backend/app/models/user.py`, add `Boolean` to the SQLAlchemy import (`from sqlalchemy import Boolean, DateTime, Enum, Integer, String`), and add these two columns after `onboarding_completed_at`:

```python
    # Manuell in der DB gesetzt - kein Self-Signup-Pfad zu Admin-Rechten.
    # Steuert Zugriff auf /api/admin/* (siehe app/routers/admin.py) und
    # den /admin-Frontend-Bereich. Siehe Design-Spec
    # "Master-Admin-Dashboard".
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Deaktivierte Accounts können sich nicht mehr einloggen (siehe
    # get_current_user-Aufrufer in auth.py `login`/`google_callback`) -
    # bestehende Sessions bleiben bis zum nächsten Login-Versuch gültig
    # (kein aktives Invalidieren in v1).
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
```

- [ ] **Step 4: Write the Alembic migration**

Create `backend/alembic/versions/0005_admin_fields.py`:

```python
"""is_admin/is_active on users

Revision ID: 0005_admin_fields
Revises: 0004_email_token_new_email
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_admin_fields"
down_revision = "0004_email_token_new_email"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("users", "is_active")
    op.drop_column("users", "is_admin")
```

Before writing this file, run `cd backend && .venv/Scripts/python -m alembic heads` to confirm `0004_email_token_new_email` is really the current head - if a different revision is the head, use that as `down_revision` instead.

- [ ] **Step 5: Add `is_admin` to `UserOut`**

In `backend/app/schemas/auth.py`, add `is_admin: bool` to `UserOut` (after `onboarding_completed_at: datetime | None`):

```python
    onboarding_completed_at: datetime | None
    is_admin: bool
```

- [ ] **Step 6: Add `require_admin` dependency**

In `backend/app/routers/auth.py`, add this function right after `get_current_user` (after its closing `return user` at line 99):

```python
def require_admin(user: User = Depends(get_current_user)) -> User:
    """FastAPI-Dependency für /api/admin/* - baut auf get_current_user auf
    (muss also erst eingeloggt sein) und prüft zusätzlich is_admin. Wirft
    403, kein 404 - es gibt keinen Grund, die Existenz des Admin-Bereichs
    vor einem eingeloggten, aber nicht-privilegierten User zu verstecken,
    da der Endpunkt-Pfad selbst schon öffentlich im Frontend-Bundle liegt."""
    if not user.is_admin:
        raise HTTPException(403, "Admin access required")
    return user
```

- [ ] **Step 7: Apply the migration to the test/dev DB and run tests**

Run: `cd backend && .venv/Scripts/python -m alembic upgrade head`
Then run: `cd backend && .venv/Scripts/python -m pytest tests/test_auth_router.py -v`
Expected: all PASS, including the 3 new tests.

- [ ] **Step 8: Run the full backend test suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all PASS except the pre-existing, unrelated `test_gemini_key_is_scoped_per_account` failure (known issue, not caused by this change).

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/user.py backend/alembic/versions/0005_admin_fields.py backend/app/schemas/auth.py backend/app/routers/auth.py backend/tests/test_auth_router.py
git commit -m "feat: add is_admin/is_active fields to User + require_admin dependency"
```

---

### Task 2: Enforce `is_active` at login (password + Google OAuth)

**Files:**
- Modify: `backend/app/routers/auth.py`
- Test: `backend/tests/test_auth_router.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_auth_router.py`:

```python
def test_login_rejects_deactivated_account(client, db_session):
    user = _make_user(db_session)
    user.is_active = False
    db_session.commit()

    response = client.post(
        "/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"}
    )
    assert response.status_code == 403
    assert "session" not in response.cookies
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_auth_router.py -k deactivated -v`
Expected: FAIL (login currently succeeds regardless of `is_active`, returns 200).

- [ ] **Step 3: Add the check to `login`**

In `backend/app/routers/auth.py`, in the `login` function, add the check right after the existing `email_verified_at` check:

```python
    if user.email_verified_at is None:
        raise HTTPException(403, "Please verify your email address first")
    if not user.is_active:
        raise HTTPException(403, "This account has been disabled. Contact support.")
```

- [ ] **Step 4: Add the same check to `google_callback`**

In `backend/app/routers/auth.py`, in `google_callback`, right after the `if user is None:` block finishes (i.e. right before the final `session_token = create_session_token(user.id)` line near the end of the function), add:

```python
    if not user.is_active:
        return RedirectResponse(
            url=f"{settings.frontend_base_url.rstrip('/')}/login?error=account_disabled"
        )

    session_token = create_session_token(user.id)
```

(This replaces the plain `session_token = create_session_token(user.id)` line - keep everything after it unchanged.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_auth_router.py -v`
Expected: all PASS.

- [ ] **Step 6: Run the full backend test suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all PASS except the pre-existing `test_gemini_key_is_scoped_per_account` failure.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/auth.py backend/tests/test_auth_router.py
git commit -m "feat: reject login for deactivated accounts (password + Google OAuth)"
```

---

### Task 3: Admin router - overview, account list, account detail, deactivate/reactivate

**Files:**
- Create: `backend/app/schemas/admin.py`
- Create: `backend/app/routers/admin.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_admin_router.py`

- [ ] **Step 1: Write the schemas**

Create `backend/app/schemas/admin.py`:

```python
"""Schemas für den Master-Admin-Bereich - siehe Design-Spec
"Master-Admin-Dashboard". Alle Endpunkte, die diese Schemas nutzen,
liegen hinter require_admin (app/routers/auth.py)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.user import AccountType


class AdminOverviewOut(BaseModel):
    total_accounts: int
    single_accounts: int
    coach_accounts: int
    active_subscriptions: int
    signups_this_week: int
    signups_this_month: int


class AdminAccountOut(BaseModel):
    id: int
    email: str
    display_name: str
    account_type: AccountType
    created_at: datetime
    subscription_status: str | None
    subscription_tier: str | None
    client_count: int
    is_active: bool
    is_admin: bool
    last_activity_at: datetime | None
    activity_status: Literal["active", "inactive", "never"]

    class Config:
        from_attributes = True


class AdminClientSummaryOut(BaseModel):
    id: int
    name: str
    photo_count: int
    last_activity_at: datetime | None


class AdminAccountDetailOut(AdminAccountOut):
    clients: list[AdminClientSummaryOut]


class AdminSetActiveRequest(BaseModel):
    is_active: bool
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_admin_router.py`:

```python
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
```

Read `backend/app/models/client.py` and `backend/app/models/photo.py` first to confirm the exact constructor field names used above (`owner_id`, `client_id`, `original_path`, `taken_at`, `status`) match reality - adjust the test fixtures if any field name differs.

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_admin_router.py -v`
Expected: FAIL (404s - `/api/admin/*` routes don't exist yet).

- [ ] **Step 4: Write the router**

Create `backend/app/routers/admin.py`:

```python
"""Master-Admin-Bereich - siehe Design-Spec "Master-Admin-Dashboard".
Alle Routen hinter require_admin (app/routers/auth.py)."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.checkin_submission import CheckinSubmission
from app.models.client import Client
from app.models.day_log import DayLog
from app.models.photo import Photo
from app.models.user import AccountType, User
from app.routers.auth import require_admin
from app.schemas.admin import (
    AdminAccountDetailOut,
    AdminAccountOut,
    AdminClientSummaryOut,
    AdminOverviewOut,
    AdminSetActiveRequest,
)

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])

# Wie active/inactive bestimmt wird - konsistent mit dem 14-Tage-Fenster
# aus der Design-Spec. "never" (kein last_activity_at) wird separat
# behandelt, siehe _activity_status.
ACTIVITY_WINDOW_DAYS = 14


def _activity_status(last_activity_at: datetime | None) -> str:
    if last_activity_at is None:
        return "never"
    cutoff = datetime.now(timezone.utc) - timedelta(days=ACTIVITY_WINDOW_DAYS)
    compare_at = last_activity_at
    if compare_at.tzinfo is None:
        compare_at = compare_at.replace(tzinfo=timezone.utc)
    return "active" if compare_at >= cutoff else "inactive"


def _last_activity_for_client_ids(db: Session, client_ids: list[int]) -> dict[int, datetime]:
    """Jüngster Zeitstempel je client_id über DayLog/Photo/CheckinSubmission
    hinweg - drei separate MAX()-Queries statt einem UNION, weil die
    Datenmenge klein ist und das lesbarer bleibt (siehe Design-Spec)."""
    if not client_ids:
        return {}
    result: dict[int, datetime] = {}

    def _merge(rows):
        for client_id, ts in rows:
            if ts is None:
                continue
            if client_id not in result or ts > result[client_id]:
                result[client_id] = ts

    day_log_rows = (
        db.query(DayLog.client_id, func.max(DayLog.date))
        .filter(DayLog.client_id.in_(client_ids))
        .group_by(DayLog.client_id)
        .all()
    )
    _merge(
        (client_id, datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc))
        for client_id, d in day_log_rows
        if d is not None
    )

    photo_rows = (
        db.query(Photo.client_id, func.max(Photo.taken_at))
        .filter(Photo.client_id.in_(client_ids))
        .group_by(Photo.client_id)
        .all()
    )
    _merge(photo_rows)

    checkin_rows = (
        db.query(CheckinSubmission.client_id, func.max(CheckinSubmission.submitted_at))
        .filter(CheckinSubmission.client_id.in_(client_ids))
        .group_by(CheckinSubmission.client_id)
        .all()
    )
    _merge(checkin_rows)

    return result


def _account_out(
    user: User, client_count: int, last_activity_at: datetime | None
) -> AdminAccountOut:
    return AdminAccountOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        account_type=user.account_type,
        created_at=user.created_at,
        subscription_status=user.subscription_status,
        subscription_tier=user.subscription_tier,
        client_count=client_count,
        is_active=user.is_active,
        is_admin=user.is_admin,
        last_activity_at=last_activity_at,
        activity_status=_activity_status(last_activity_at),
    )


@router.get("/overview", response_model=AdminOverviewOut)
def overview(db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    total_accounts = db.query(func.count(User.id)).scalar() or 0
    single_accounts = (
        db.query(func.count(User.id)).filter(User.account_type == AccountType.SINGLE).scalar() or 0
    )
    coach_accounts = (
        db.query(func.count(User.id)).filter(User.account_type == AccountType.COACH).scalar() or 0
    )
    active_subscriptions = (
        db.query(func.count(User.id))
        .filter(User.subscription_status.in_(["active", "trialing"]))
        .scalar()
        or 0
    )
    signups_this_week = (
        db.query(func.count(User.id)).filter(User.created_at >= week_ago).scalar() or 0
    )
    signups_this_month = (
        db.query(func.count(User.id)).filter(User.created_at >= month_ago).scalar() or 0
    )

    return AdminOverviewOut(
        total_accounts=total_accounts,
        single_accounts=single_accounts,
        coach_accounts=coach_accounts,
        active_subscriptions=active_subscriptions,
        signups_this_week=signups_this_week,
        signups_this_month=signups_this_month,
    )


@router.get("/accounts", response_model=list[AdminAccountOut])
def list_accounts(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    user_ids = [u.id for u in users]

    client_counts = dict(
        db.query(Client.owner_id, func.count(Client.id))
        .filter(Client.owner_id.in_(user_ids))
        .group_by(Client.owner_id)
        .all()
    )
    client_ids_by_owner: dict[int, list[int]] = {}
    for owner_id, client_id in db.query(Client.owner_id, Client.id).filter(
        Client.owner_id.in_(user_ids)
    ).all():
        client_ids_by_owner.setdefault(owner_id, []).append(client_id)

    all_client_ids = [cid for ids in client_ids_by_owner.values() for cid in ids]
    activity_by_client = _last_activity_for_client_ids(db, all_client_ids)

    results = []
    for user in users:
        owned_client_ids = client_ids_by_owner.get(user.id, [])
        last_activity_at = None
        for cid in owned_client_ids:
            ts = activity_by_client.get(cid)
            if ts is not None and (last_activity_at is None or ts > last_activity_at):
                last_activity_at = ts
        results.append(_account_out(user, client_counts.get(user.id, 0), last_activity_at))
    return results


@router.get("/accounts/{user_id}", response_model=AdminAccountDetailOut)
def get_account(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Account not found")

    clients = db.query(Client).filter(Client.owner_id == user_id).all()
    client_ids = [c.id for c in clients]
    activity_by_client = _last_activity_for_client_ids(db, client_ids)
    photo_counts = dict(
        db.query(Photo.client_id, func.count(Photo.id))
        .filter(Photo.client_id.in_(client_ids))
        .group_by(Photo.client_id)
        .all()
    )

    client_summaries = [
        AdminClientSummaryOut(
            id=c.id,
            name=c.name,
            photo_count=photo_counts.get(c.id, 0),
            last_activity_at=activity_by_client.get(c.id),
        )
        for c in clients
    ]
    last_activity_at = max(
        (s.last_activity_at for s in client_summaries if s.last_activity_at is not None),
        default=None,
    )

    base = _account_out(user, len(clients), last_activity_at)
    return AdminAccountDetailOut(**base.model_dump(), clients=client_summaries)


@router.patch("/accounts/{user_id}", response_model=AdminAccountOut)
def set_account_active(
    user_id: int,
    payload: AdminSetActiveRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    if user_id == current_admin.id:
        raise HTTPException(400, "Cannot deactivate your own account")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Account not found")

    user.is_active = payload.is_active
    db.commit()
    db.refresh(user)

    client_count = db.query(func.count(Client.id)).filter(Client.owner_id == user_id).scalar() or 0
    client_ids = [c.id for c in db.query(Client.id).filter(Client.owner_id == user_id).all()]
    activity = _last_activity_for_client_ids(db, [cid for (cid,) in client_ids] if client_ids and isinstance(client_ids[0], tuple) else client_ids)
    last_activity_at = max(activity.values(), default=None)
    return _account_out(user, client_count, last_activity_at)
```

IMPORTANT while implementing: the line building `client_ids` in `set_account_active` has a defensive but confusing tuple-unwrap - simplify it. Read the actual result shape of `db.query(Client.id).filter(...).all()` (it's a list of 1-tuples) and write it cleanly, e.g.:

```python
    client_ids = [row[0] for row in db.query(Client.id).filter(Client.owner_id == user_id).all()]
    activity = _last_activity_for_client_ids(db, client_ids)
```

Replace the confusing line with this clean version before running tests.

Also double check `Client`'s owner FK column name (`owner_id` assumed above) against `backend/app/models/client.py` - adjust every `Client.owner_id` reference in this file if the actual column is named differently.

- [ ] **Step 5: Register the router**

In `backend/app/main.py`, add the import and registration alongside the existing ones:

```python
from app.routers import admin
```

(add to whatever existing `from app.routers import ...` block already lists `auth, clients, dashboard, ...` - match the existing import style exactly)

```python
app.include_router(admin.router)
```

(add after `app.include_router(billing.router)`)

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_admin_router.py -v`
Expected: all PASS. If any fail due to field-name mismatches (`Client`/`Photo` constructor args), fix the test fixtures to match the real model definitions and re-run.

- [ ] **Step 7: Run the full backend test suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all PASS except the pre-existing `test_gemini_key_is_scoped_per_account` failure.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/admin.py backend/app/routers/admin.py backend/app/main.py backend/tests/test_admin_router.py
git commit -m "feat: add admin router (overview, account list/detail, deactivate/reactivate)"
```

---

### Task 4: Frontend types + API client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add admin types**

In `frontend/src/types/index.ts`, add at the end of the file:

```typescript
export interface AdminOverview {
  total_accounts: number;
  single_accounts: number;
  coach_accounts: number;
  active_subscriptions: number;
  signups_this_week: number;
  signups_this_month: number;
}

export interface AdminAccount {
  id: number;
  email: string;
  display_name: string;
  account_type: "single" | "coach";
  created_at: string;
  subscription_status: string | null;
  subscription_tier: string | null;
  client_count: number;
  is_active: boolean;
  is_admin: boolean;
  last_activity_at: string | null;
  activity_status: "active" | "inactive" | "never";
}

export interface AdminClientSummary {
  id: number;
  name: string;
  photo_count: number;
  last_activity_at: string | null;
}

export interface AdminAccountDetail extends AdminAccount {
  clients: AdminClientSummary[];
}
```

- [ ] **Step 2: Add `is_admin` to `CurrentUser` and the `admin` API namespace**

In `frontend/src/api/client.ts`:

Add to the type import line (alphabetized among existing entries): `AdminAccount, AdminAccountDetail, AdminOverview,`

Add `is_admin: boolean;` to the `CurrentUser` interface, right after `onboarding_completed_at: string | null;`:

```typescript
  onboarding_completed_at: string | null;
  is_admin: boolean;
```

Add a new `admin` namespace to the `api` object (alongside `dashboard`, `billing`, `auth`, etc.):

```typescript
  admin: {
    overview: () => client.get<AdminOverview>("/admin/overview").then((r) => r.data),
    listAccounts: () => client.get<AdminAccount[]>("/admin/accounts").then((r) => r.data),
    getAccount: (userId: number) =>
      client.get<AdminAccountDetail>(`/admin/accounts/${userId}`).then((r) => r.data),
    setAccountActive: (userId: number, isActive: boolean) =>
      client
        .patch<AdminAccount>(`/admin/accounts/${userId}`, { is_active: isActive })
        .then((r) => r.data),
  },
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors (nothing consumes the new `admin` namespace yet, so nothing should break).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/client.ts
git commit -m "feat: add admin types and API client namespace"
```

---

### Task 5: `/admin` route - guard, overview+accounts page, account detail page

**Files:**
- Create: `frontend/src/components/AdminGuard.tsx`
- Create: `frontend/src/pages/Admin.tsx`
- Create: `frontend/src/pages/AdminAccountDetail.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Write the guard component**

Create `frontend/src/components/AdminGuard.tsx`:

```tsx
import { Navigate, Outlet } from "react-router-dom";
import { useCurrentUser } from "../hooks/useCurrentUser";

/** Schützt /admin/* - dieselbe Logik wie RequireAuth, zusätzlich muss
 * is_admin true sein. Bewusst KEIN Unterschied in der Fehlerbehandlung
 * zwischen "nicht eingeloggt" und "kein Admin" - beides landet auf
 * /login, um die Existenz des Admin-Bereichs nicht zu verraten (siehe
 * Design-Spec "Master-Admin-Dashboard"). */
export default function AdminGuard() {
  const { data: user, isLoading, isError } = useCurrentUser();

  if (isLoading) return null;
  if (isError || !user || !user.is_admin) return <Navigate to="/login" replace />;

  return <Outlet />;
}
```

- [ ] **Step 2: Write the overview+accounts page**

Create `frontend/src/pages/Admin.tsx`:

```tsx
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { Card } from "../components/Card";

const ACTIVITY_LABEL: Record<string, string> = {
  active: "🟢 Active",
  inactive: "⚪ Inactive",
  never: "— Never",
};

export default function Admin() {
  const [search, setSearch] = useState("");

  const overviewQuery = useQuery({ queryKey: ["admin", "overview"], queryFn: api.admin.overview });
  const accountsQuery = useQuery({ queryKey: ["admin", "accounts"], queryFn: api.admin.listAccounts });

  const filteredAccounts = (accountsQuery.data ?? []).filter((a) =>
    a.email.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="min-h-screen bg-background px-6 py-8 text-slate-100">
      <div className="mx-auto max-w-6xl space-y-6">
        <h1 className="text-2xl font-semibold text-white">Admin</h1>

        {overviewQuery.data && (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            <Card title="Total Accounts">
              <p className="text-2xl font-semibold text-white">{overviewQuery.data.total_accounts}</p>
            </Card>
            <Card title="Single">
              <p className="text-2xl font-semibold text-white">{overviewQuery.data.single_accounts}</p>
            </Card>
            <Card title="Coach">
              <p className="text-2xl font-semibold text-white">{overviewQuery.data.coach_accounts}</p>
            </Card>
            <Card title="Active Subs">
              <p className="text-2xl font-semibold text-white">{overviewQuery.data.active_subscriptions}</p>
            </Card>
            <Card title="Signups (7d / 30d)">
              <p className="text-2xl font-semibold text-white">
                {overviewQuery.data.signups_this_week} / {overviewQuery.data.signups_this_month}
              </p>
            </Card>
          </div>
        )}

        <Card title="Accounts">
          <input
            type="text"
            placeholder="Search by email…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="mb-4 w-full max-w-sm rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white focus:border-accent focus:outline-none"
          />
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-slate-400">
                <tr>
                  <th className="pb-2 pr-4">Email</th>
                  <th className="pb-2 pr-4">Type</th>
                  <th className="pb-2 pr-4">Signup</th>
                  <th className="pb-2 pr-4">Subscription</th>
                  <th className="pb-2 pr-4">Clients</th>
                  <th className="pb-2 pr-4">Activity</th>
                  <th className="pb-2 pr-4">Status</th>
                </tr>
              </thead>
              <tbody>
                {filteredAccounts.map((a) => (
                  <tr key={a.id} className="border-t border-white/5">
                    <td className="py-2 pr-4">
                      <Link to={`/admin/accounts/${a.id}`} className="text-accent hover:underline">
                        {a.email}
                      </Link>
                    </td>
                    <td className="py-2 pr-4">{a.account_type}</td>
                    <td className="py-2 pr-4">{new Date(a.created_at).toLocaleDateString("en-US")}</td>
                    <td className="py-2 pr-4">{a.subscription_tier ?? "—"}</td>
                    <td className="py-2 pr-4">{a.client_count}</td>
                    <td className="py-2 pr-4">{ACTIVITY_LABEL[a.activity_status]}</td>
                    <td className="py-2 pr-4">
                      {a.is_active ? (
                        <span className="text-green-400">Active</span>
                      ) : (
                        <span className="text-red-400">Disabled</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Write the account detail page**

Create `frontend/src/pages/AdminAccountDetail.tsx`:

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { Card } from "../components/Card";

export default function AdminAccountDetail() {
  const { userId } = useParams<{ userId: string }>();
  const userIdNum = Number(userId);
  const queryClient = useQueryClient();

  const accountQuery = useQuery({
    queryKey: ["admin", "accounts", userIdNum],
    queryFn: () => api.admin.getAccount(userIdNum),
    enabled: !Number.isNaN(userIdNum),
  });

  const toggleActiveMutation = useMutation({
    mutationFn: (isActive: boolean) => api.admin.setAccountActive(userIdNum, isActive),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "accounts", userIdNum] });
      queryClient.invalidateQueries({ queryKey: ["admin", "accounts"] });
    },
  });

  if (accountQuery.isLoading) {
    return <div className="min-h-screen bg-background px-6 py-8 text-slate-400">Loading…</div>;
  }
  if (accountQuery.isError || !accountQuery.data) {
    return <div className="min-h-screen bg-background px-6 py-8 text-slate-400">Account not found.</div>;
  }

  const account = accountQuery.data;

  return (
    <div className="min-h-screen bg-background px-6 py-8 text-slate-100">
      <div className="mx-auto max-w-3xl space-y-6">
        <Link to="/admin" className="text-sm text-accent hover:underline">
          ← Back to accounts
        </Link>
        <h1 className="text-2xl font-semibold text-white">{account.email}</h1>

        <Card title="Account">
          <dl className="grid grid-cols-2 gap-y-2 text-sm">
            <dt className="text-slate-400">Type</dt>
            <dd className="text-white">{account.account_type}</dd>
            <dt className="text-slate-400">Signup</dt>
            <dd className="text-white">{new Date(account.created_at).toLocaleDateString("en-US")}</dd>
            <dt className="text-slate-400">Subscription</dt>
            <dd className="text-white">
              {account.subscription_tier ?? "—"} ({account.subscription_status ?? "none"})
            </dd>
            <dt className="text-slate-400">Status</dt>
            <dd className={account.is_active ? "text-green-400" : "text-red-400"}>
              {account.is_active ? "Active" : "Disabled"}
            </dd>
          </dl>
          <button
            onClick={() => toggleActiveMutation.mutate(!account.is_active)}
            disabled={toggleActiveMutation.isPending}
            className={`mt-4 rounded-lg px-4 py-2 text-sm font-medium disabled:opacity-50 ${
              account.is_active
                ? "bg-red-900/40 text-red-300 hover:bg-red-900/60"
                : "bg-accent text-slate-900 hover:opacity-90"
            }`}
          >
            {toggleActiveMutation.isPending
              ? "Saving…"
              : account.is_active
                ? "Deactivate account"
                : "Reactivate account"}
          </button>
        </Card>

        <Card title="Clients">
          {account.clients.length === 0 && <p className="text-sm text-slate-500">No clients.</p>}
          <ul className="space-y-2">
            {account.clients.map((c) => (
              <li key={c.id} className="flex items-center justify-between text-sm">
                <span className="text-white">{c.name}</span>
                <span className="text-slate-400">
                  {c.photo_count} photos ·{" "}
                  {c.last_activity_at
                    ? new Date(c.last_activity_at).toLocaleDateString("en-US")
                    : "no activity"}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Wire the routes into `App.tsx`**

In `frontend/src/App.tsx`, add the imports (alongside the existing page imports):

```tsx
import AdminGuard from "./components/AdminGuard";
import Admin from "./pages/Admin";
import AdminAccountDetail from "./pages/AdminAccountDetail";
```

Add a new top-level route block, placed alongside the existing `<Route element={<RequireAuth />}>` block (as a sibling, NOT nested inside it or inside `AppShell`/`ClientShell`):

```tsx
      <Route element={<AdminGuard />}>
        <Route path="admin" element={<Admin />} />
        <Route path="admin/accounts/:userId" element={<AdminAccountDetail />} />
      </Route>
```

- [ ] **Step 5: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/AdminGuard.tsx frontend/src/pages/Admin.tsx frontend/src/pages/AdminAccountDetail.tsx frontend/src/App.tsx
git commit -m "feat: add /admin overview+accounts page and account detail page"
```

---

### Task 6: Holistic review + finish branch

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all PASS except the pre-existing, unrelated `test_gemini_key_is_scoped_per_account` failure.

- [ ] **Step 2: Run frontend type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Manual review checklist**

- Confirm `require_admin` genuinely blocks a logged-in non-admin (403) and an anonymous request (401) on every `/api/admin/*` route.
- Confirm a deactivated account cannot log in via password (`test_login_rejects_deactivated_account`) - and read through the Google OAuth callback change once more to confirm the redirect-based rejection reads correctly (no automated test for the OAuth path per the plan's own scope note - mocking Google's OAuth flow is out of scope here).
- Confirm the admin's own account cannot be deactivated via `PATCH /api/admin/accounts/{own_id}`.
- Confirm `/admin` has no visible link anywhere in the existing navigation (`ClientShell.tsx`, `AppShell.tsx`) - it must stay URL-only per the design spec.
- Confirm no `alembic upgrade head` step was skipped - the new columns must actually exist for the deployed DB (this matters for the eventual production deploy, not just local dev).

- [ ] **Step 4: Use the finishing-a-development-branch skill**

Invoke `superpowers:finishing-a-development-branch` to push per the user's standing "option 1" preference (this session works directly on `dev`).
