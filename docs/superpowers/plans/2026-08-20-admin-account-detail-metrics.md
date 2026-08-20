# Admin Account-Detail Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the Master-Admin account-detail page with three new metric groups: total check-ins across the account, storage usage (photo file sizes, known-going-forward), and live Stripe billing details (next billing date, recent invoices) — without duplicating billing state or backfilling historical photo sizes.

**Architecture:** (a) Total check-ins is a pure aggregation added to the existing `GET /api/admin/accounts/{user_id}` response. (b) Storage usage requires a new nullable `file_size_bytes` column on `Photo`, populated going forward at photo-sync time (`services/folder_sync.py`, right after the on-disk file is finalized), summed (with an "unknown size" counter for photos predating this column) into the same admin response. (c) Billing details are fetched live from Stripe on a separate, lazily-loaded endpoint (`GET /api/admin/accounts/{user_id}/billing`) using the account's existing `stripe_customer_id` — nothing new is persisted.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (backend), React + TanStack Query + TypeScript + Tailwind (frontend), pytest with `monkeypatch` for Stripe mocking (matching the existing pattern in `tests/test_billing_router.py`).

---

### Task 1: `file_size_bytes` on Photo — migration + populate at sync time

**Files:**
- Modify: `backend/app/models/photo.py`
- Create: `backend/alembic/versions/0006_photo_file_size.py`
- Modify: `backend/app/services/folder_sync.py`
- Test: `backend/tests/test_folder_sync.py` (create if it doesn't exist, else extend)

- [ ] **Step 1: Check whether a folder_sync test file already exists**

Run: `ls backend/tests/test_folder_sync.py`

If it exists, read it fully before writing new tests (Step 2) so you match its existing fixture/helper style. If it doesn't exist, Step 2 creates it from scratch using the `client`/`db_session` fixtures already used throughout `backend/tests/` (see `backend/tests/test_admin_router.py` for the pattern — no new fixtures needed).

- [ ] **Step 2: Write the failing test**

Add to `backend/tests/test_folder_sync.py` (create the file with this content if it doesn't exist yet; if it exists, append this test):

```python
from pathlib import Path

from app.core.config import settings
from app.models.client import Client
from app.services.folder_sync import sync_incoming_folder
from app.services.storage_paths import incoming_dir_for_client


def _make_client(db_session):
    from app.models.user import User
    from app.services.auth import hash_password
    from datetime import datetime, timezone

    owner = User(
        email="sync-owner@example.com",
        password_hash=hash_password("Grindcore123!"),
        display_name="Owner",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    client_row = Client(owner_id=owner.id, name="Sync Client")
    db_session.add(client_row)
    db_session.commit()
    db_session.refresh(client_row)
    return client_row


def test_sync_populates_file_size_bytes(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    client_row = _make_client(db_session)

    incoming_dir = incoming_dir_for_client(client_row.id)
    incoming_dir.mkdir(parents=True, exist_ok=True)

    from PIL import Image

    img_path = incoming_dir / "photo.jpg"
    Image.new("RGB", (100, 100), color="red").save(img_path, format="JPEG")

    photos = sync_incoming_folder(db_session, client_row.id)

    assert len(photos) == 1
    assert photos[0].file_size_bytes is not None
    assert photos[0].file_size_bytes > 0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_folder_sync.py::test_sync_populates_file_size_bytes -v`
Expected: FAIL — `AttributeError: 'Photo' object has no attribute 'file_size_bytes'` (column doesn't exist yet).

- [ ] **Step 4: Add the column to the `Photo` model**

In `backend/app/models/photo.py`, add this field right after the `width`/`height` fields (after line 100, before `created_at`):

```python
    # Größe der Originaldatei in Bytes, direkt nach dem finalen
    # Schreiben/Komprimieren erfasst (services/folder_sync.py) - für den
    # Speicherverbrauch im Master-Admin-Bereich. NULL für Fotos, die vor
    # Einführung dieser Spalte synchronisiert wurden (kein rückwirkendes
    # Backfill, siehe Design-Spec "Master-Admin: Account-Detail-
    # Kennzahlen" Abschnitt b).
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

- [ ] **Step 5: Create the Alembic migration**

Write `backend/alembic/versions/0006_photo_file_size.py`:

```python
"""file_size_bytes on photos

Revision ID: 0006_photo_file_size
Revises: 0005_admin_fields
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_photo_file_size"
down_revision = "0005_admin_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "photos",
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("photos", "file_size_bytes")
```

- [ ] **Step 6: Populate the field in `sync_incoming_folder`**

In `backend/app/services/folder_sync.py`, find this block inside `sync_incoming_folder`:

```python
        photo = Photo(
            client_id=client_id,
            filename=file.name,
            original_path=rel_path,
            preview_path=preview_rel_path,
            thumbnail_path=thumb_rel_path,
            taken_at=taken_at,
            width=width,
            height=height,
        )
```

Replace it with (adds `file_size_bytes=file.stat().st_size`, read right before the `Photo` row is built — at this point `_compress_original_in_place` has already finished for non-HEIC files, so this reflects the actual final on-disk size, matching what gets pushed to storage a few lines below):

```python
        photo = Photo(
            client_id=client_id,
            filename=file.name,
            original_path=rel_path,
            preview_path=preview_rel_path,
            thumbnail_path=thumb_rel_path,
            taken_at=taken_at,
            width=width,
            height=height,
            file_size_bytes=file.stat().st_size,
        )
```

- [ ] **Step 7: Run the migration locally and run the test**

Run: `cd backend && .venv/Scripts/python -m alembic upgrade head`
Expected: migration `0006_photo_file_size` applies cleanly.

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_folder_sync.py -v`
Expected: PASS.

- [ ] **Step 8: Run the full backend suite to check for regressions**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: same pass count as before this change, plus the 1 new test (only the pre-existing unrelated flaky `test_gemini_key_is_scoped_per_account` may fail — that's expected and unrelated).

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/photo.py backend/alembic/versions/0006_photo_file_size.py backend/app/services/folder_sync.py backend/tests/test_folder_sync.py
git commit -m "feat: track photo file size at sync time"
```

---

### Task 2: Total check-ins + storage usage on the admin account-detail endpoint

**Files:**
- Modify: `backend/app/schemas/admin.py`
- Modify: `backend/app/routers/admin.py`
- Test: `backend/tests/test_admin_router.py`

- [ ] **Step 1: Extend `AdminAccountDetailOut`**

In `backend/app/schemas/admin.py`, replace:

```python
class AdminAccountDetailOut(AdminAccountOut):
    clients: list[AdminClientSummaryOut]
```

with:

```python
class AdminAccountDetailOut(AdminAccountOut):
    clients: list[AdminClientSummaryOut]
    total_checkins: int
    total_storage_bytes: int
    photos_with_unknown_size: int
```

- [ ] **Step 2: Write the failing tests**

Append to `backend/tests/test_admin_router.py` (read the existing file first — it already has `_make_user`/`_login_as` helpers you should reuse, don't redefine them):

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_admin_router.py -k "total_checkins or photo_sizes" -v`
Expected: FAIL — pydantic `ValidationError: Field required` for `total_checkins`/`total_storage_bytes`/`photos_with_unknown_size` (fields don't exist on the response yet).

- [ ] **Step 4: Implement the aggregation in `get_account`**

In `backend/app/routers/admin.py`, add this import at the top (extend the existing `from app.models.checkin_submission import CheckinSubmission` import — check if it's already imported; if not, add it):

```python
from app.models.checkin_submission import CheckinSubmission
```

Then, inside `get_account(...)`, right before the final `return AdminAccountDetailOut(**base.model_dump(), clients=client_summaries)` line, insert:

```python
    total_checkins = (
        db.query(func.count(CheckinSubmission.id))
        .filter(CheckinSubmission.client_id.in_(client_ids))
        .scalar()
        or 0
    )

    storage_rows = (
        db.query(Photo.file_size_bytes).filter(Photo.client_id.in_(client_ids)).all()
    )
    total_storage_bytes = sum(size for (size,) in storage_rows if size is not None)
    photos_with_unknown_size = sum(1 for (size,) in storage_rows if size is None)
```

Then update the return statement:

```python
    return AdminAccountDetailOut(
        **base.model_dump(),
        clients=client_summaries,
        total_checkins=total_checkins,
        total_storage_bytes=total_storage_bytes,
        photos_with_unknown_size=photos_with_unknown_size,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_admin_router.py -v`
Expected: all tests PASS (previous admin router tests + 2 new).

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: same as Task 1's Step 8 plus these 2 new tests, all passing (aside from the known unrelated flaky test).

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/admin.py backend/app/routers/admin.py backend/tests/test_admin_router.py
git commit -m "feat: add total check-ins and storage usage to admin account detail"
```

---

### Task 3: Live Stripe billing details endpoint

**Files:**
- Modify: `backend/app/schemas/admin.py`
- Modify: `backend/app/routers/admin.py`
- Test: `backend/tests/test_admin_router.py`

- [ ] **Step 1: Add the billing response schema**

In `backend/app/schemas/admin.py`, add at the end of the file:

```python
class AdminInvoiceOut(BaseModel):
    amount: float
    currency: str
    paid_at: datetime | None
    status: str


class AdminBillingOut(BaseModel):
    has_stripe_customer: bool
    subscription_id: str | None
    next_billing_date: datetime | None
    recent_invoices: list[AdminInvoiceOut]
```

- [ ] **Step 2: Write the failing tests**

Append to `backend/tests/test_admin_router.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_admin_router.py -k billing -v`
Expected: FAIL — 404 (route doesn't exist yet).

- [ ] **Step 4: Implement the endpoint**

In `backend/app/routers/admin.py`, add `stripe` and `logging` to the imports at the top:

```python
import logging

import stripe
```

Add this near the top of the file, after the `router = APIRouter(...)` line:

```python
logger = logging.getLogger(__name__)
```

Add the schema import (extend the existing `from app.schemas.admin import (...)` block):

```python
from app.schemas.admin import (
    AdminAccountDetailOut,
    AdminAccountOut,
    AdminBillingOut,
    AdminClientSummaryOut,
    AdminInvoiceOut,
    AdminOverviewOut,
    AdminSetActiveRequest,
)
```

Then add the new endpoint, right after `get_account`:

```python
@router.get("/accounts/{user_id}/billing", response_model=AdminBillingOut)
def get_account_billing(user_id: int, db: Session = Depends(get_db)):
    """Fragt Billing-Details LIVE von Stripe ab statt sie zu spiegeln
    (vermeidet Stale-Data) - siehe Design-Spec "Master-Admin:
    Account-Detail-Kennzahlen" Abschnitt c). Eigener Endpunkt statt Teil
    von get_account(), damit die Haupt-Detailseite nicht bei jedem Aufruf
    auf einen zusätzlichen Stripe-Roundtrip wartet."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Account not found")

    if not user.stripe_customer_id:
        return AdminBillingOut(
            has_stripe_customer=False,
            subscription_id=None,
            next_billing_date=None,
            recent_invoices=[],
        )

    subscription_id: str | None = None
    next_billing_date: datetime | None = None
    recent_invoices: list[AdminInvoiceOut] = []

    try:
        subscriptions = stripe.Subscription.list(customer=user.stripe_customer_id, limit=1)
        if subscriptions["data"]:
            sub = subscriptions["data"][0]
            subscription_id = sub["id"]
            next_billing_date = datetime.fromtimestamp(
                sub["current_period_end"], tz=timezone.utc
            )
    except Exception:
        logger.warning(
            "Konnte Stripe-Subscription für Account %s nicht laden", user_id, exc_info=True
        )

    try:
        invoices = stripe.Invoice.list(customer=user.stripe_customer_id, limit=5)
        for inv in invoices["data"]:
            paid_at_ts = inv.get("status_transitions", {}).get("paid_at")
            recent_invoices.append(
                AdminInvoiceOut(
                    amount=inv["amount_paid"] / 100,
                    currency=inv["currency"],
                    paid_at=(
                        datetime.fromtimestamp(paid_at_ts, tz=timezone.utc)
                        if paid_at_ts
                        else None
                    ),
                    status=inv["status"],
                )
            )
    except Exception:
        logger.warning(
            "Konnte Stripe-Invoices für Account %s nicht laden", user_id, exc_info=True
        )

    return AdminBillingOut(
        has_stripe_customer=True,
        subscription_id=subscription_id,
        next_billing_date=next_billing_date,
        recent_invoices=recent_invoices,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_admin_router.py -v`
Expected: all tests PASS.

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all passing aside from the known unrelated flaky test.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/admin.py backend/app/routers/admin.py backend/tests/test_admin_router.py
git commit -m "feat: add live Stripe billing details endpoint to admin"
```

---

### Task 4: Frontend — show the new metrics on the account-detail page

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/AdminAccountDetail.tsx`

- [ ] **Step 1: Add the new types**

In `frontend/src/types/index.ts`, find:

```typescript
export interface AdminAccountDetail extends AdminAccount {
```

Read the full existing `AdminAccountDetail` interface first (it likely already has `clients: AdminClientSummary[]` or similar — match the exact existing shape before editing). Add these three fields to it: `total_checkins: number`, `total_storage_bytes: number`, `photos_with_unknown_size: number`.

Then add two new interfaces near the other Admin types:

```typescript
export interface AdminInvoice {
  amount: number;
  currency: string;
  paid_at: string | null;
  status: string;
}

export interface AdminBilling {
  has_stripe_customer: boolean;
  subscription_id: string | null;
  next_billing_date: string | null;
  recent_invoices: AdminInvoice[];
}
```

- [ ] **Step 2: Add the API client method**

In `frontend/src/api/client.ts`, inside the `admin` object, add (alongside the existing `getAccount` method):

```typescript
    getBilling: (userId: number) =>
      client.get<AdminBilling>(`/admin/accounts/${userId}/billing`).then((r) => r.data),
```

Add `AdminBilling` to the type import at the top of the file (extend the existing `import type { ... } from "../types"` line).

- [ ] **Step 3: Add a storage-size formatter helper**

In `frontend/src/pages/AdminAccountDetail.tsx`, add this helper function near the top of the file (after the imports):

```tsx
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex++;
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`;
}
```

- [ ] **Step 4: Add the new metrics to the "Account" card**

In `frontend/src/pages/AdminAccountDetail.tsx`, find the closing `</dl>` of the existing `<Card title="Account">` block:

```tsx
            <dt className="text-slate-400">Status</dt>
            <dd className={account.is_active ? "text-green-400" : "text-red-400"}>
              {account.is_active ? "Active" : "Disabled"}
            </dd>
          </dl>
```

Replace it with (adds check-ins and storage rows):

```tsx
            <dt className="text-slate-400">Status</dt>
            <dd className={account.is_active ? "text-green-400" : "text-red-400"}>
              {account.is_active ? "Active" : "Disabled"}
            </dd>
            <dt className="text-slate-400">Total check-ins</dt>
            <dd className="text-white">{account.total_checkins}</dd>
            <dt className="text-slate-400">Storage used</dt>
            <dd className="text-white">
              {formatBytes(account.total_storage_bytes)}
              {account.photos_with_unknown_size > 0 && (
                <span className="text-slate-500">
                  {" "}
                  (+{account.photos_with_unknown_size} photos with unknown size)
                </span>
              )}
            </dd>
          </dl>
```

- [ ] **Step 5: Add a lazily-loaded Billing card**

In `frontend/src/pages/AdminAccountDetail.tsx`, add this new component at the end of the file:

```tsx
function BillingCard({ userId }: { userId: number }) {
  const billingQuery = useQuery({
    queryKey: ["admin", "accounts", userId, "billing"],
    queryFn: () => api.admin.getBilling(userId),
  });

  return (
    <Card title="Billing">
      {billingQuery.isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {billingQuery.isError && (
        <p className="text-sm text-red-400">Could not load billing details.</p>
      )}
      {billingQuery.data && !billingQuery.data.has_stripe_customer && (
        <p className="text-sm text-slate-500">No Stripe customer on this account.</p>
      )}
      {billingQuery.data && billingQuery.data.has_stripe_customer && (
        <div className="space-y-3 text-sm">
          <dl className="grid grid-cols-2 gap-y-2">
            <dt className="text-slate-400">Subscription</dt>
            <dd className="text-white">{billingQuery.data.subscription_id ?? "—"}</dd>
            <dt className="text-slate-400">Next billing date</dt>
            <dd className="text-white">
              {billingQuery.data.next_billing_date
                ? new Date(billingQuery.data.next_billing_date).toLocaleDateString("en-US")
                : "—"}
            </dd>
          </dl>
          {billingQuery.data.recent_invoices.length > 0 && (
            <div>
              <p className="mb-1 text-slate-400">Recent invoices</p>
              <ul className="space-y-1">
                {billingQuery.data.recent_invoices.map((inv, i) => (
                  <li key={i} className="flex items-center justify-between text-slate-300">
                    <span>
                      {inv.paid_at ? new Date(inv.paid_at).toLocaleDateString("en-US") : "—"} ·{" "}
                      {inv.status}
                    </span>
                    <span>
                      {inv.amount.toFixed(2)} {inv.currency.toUpperCase()}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
```

Add `useQuery` and `api` are already imported at the top of the file (confirm this — `AdminAccountDetail.tsx` already imports both for its existing `accountQuery`). Then render `<BillingCard userId={userIdNum} />` right after the existing `<Card title="Clients">...</Card>` block, still inside the `<div className="mx-auto max-w-3xl space-y-6">` wrapper.

- [ ] **Step 6: Verify the frontend type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 7: Manual check in the browser**

Log in as an admin account, open `/admin`, click into an account's detail page. Verify: "Total check-ins" and "Storage used" rows appear under the existing Account card, and a new "Billing" card loads below the Clients card (showing "No Stripe customer on this account." for an account without one, or subscription/invoice details for one that has `stripe_customer_id` set).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/client.ts frontend/src/pages/AdminAccountDetail.tsx
git commit -m "feat: show total check-ins, storage usage and billing details on admin account detail"
```

---

### Task 5: Final review and finish

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all tests pass except the pre-existing unrelated flaky `test_gemini_key_is_scoped_per_account`.

- [ ] **Step 2: Run the full frontend type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Use superpowers:finishing-a-development-branch**

Follow that skill to present merge/PR/keep/discard options and complete the branch.
