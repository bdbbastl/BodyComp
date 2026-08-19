# Coach Dashboard Widgets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Coach dashboard's full client-tile grid with a 2x2 widget layout (quick client list, unseen check-ins, needs-attention, this-week stats), backed by one new aggregation endpoint.

**Architecture:** New backend router `dashboard.py` exposes `GET /api/dashboard/coach-summary` aggregating pending check-ins, quiet clients, and weekly stats across all of the current user's clients. Frontend `Dashboard.tsx` fetches this once and renders four small widget components from it, alongside the existing `api.clients.list()` data for the client-list widget.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, React, TanStack Query, TypeScript.

---

### Task 1: Backend `coach-summary` schema + endpoint

**Files:**
- Create: `backend/app/schemas/dashboard.py`
- Create: `backend/app/routers/dashboard.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_dashboard_router.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_dashboard_router.py`:

```python
from datetime import datetime, timedelta, timezone

from app.models.checkin_submission import CheckinStatus, CheckinSubmission
from app.models.client import Client
from app.models.photo import Photo, ProcessingStatus
from app.models.user import User
from app.services.auth import hash_password


def _login(client, db_session, email="coach@b.com", password="pw12345"):
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name="Coach",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    client.post("/api/auth/login", json={"email": email, "password": password})
    return user


def test_coach_summary_requires_login(client, db_session):
    response = client.get("/api/dashboard/coach-summary")
    assert response.status_code == 401


def test_coach_summary_lists_pending_checkins_across_clients(client, db_session):
    user = _login(client, db_session)
    c1 = Client(owner_id=user.id, name="Client A")
    c2 = Client(owner_id=user.id, name="Client B")
    db_session.add_all([c1, c2])
    db_session.commit()
    db_session.refresh(c1)
    db_session.refresh(c2)

    older = CheckinSubmission(
        client_id=c1.id,
        weight_kg=80.0,
        status=CheckinStatus.PENDING,
        submitted_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    newer = CheckinSubmission(
        client_id=c2.id,
        weight_kg=70.0,
        status=CheckinStatus.PENDING,
        submitted_at=datetime.now(timezone.utc),
    )
    reviewed = CheckinSubmission(
        client_id=c1.id,
        weight_kg=81.0,
        status=CheckinStatus.REVIEWED,
        submitted_at=datetime.now(timezone.utc),
    )
    db_session.add_all([older, newer, reviewed])
    db_session.commit()

    response = client.get("/api/dashboard/coach-summary")
    assert response.status_code == 200
    body = response.json()
    pending = body["pending_checkins"]
    assert len(pending) == 2
    # neueste zuerst
    assert pending[0]["client_name"] == "Client B"
    assert pending[1]["client_name"] == "Client A"


def test_coach_summary_needs_attention_uses_seven_day_threshold(client, db_session):
    user = _login(client, db_session)
    quiet_client = Client(owner_id=user.id, name="Quiet Client")
    active_client = Client(owner_id=user.id, name="Active Client")
    never_active_client = Client(owner_id=user.id, name="Never Active")
    db_session.add_all([quiet_client, active_client, never_active_client])
    db_session.commit()
    db_session.refresh(quiet_client)
    db_session.refresh(active_client)

    old_photo = Photo(
        client_id=quiet_client.id,
        filename="old.jpg",
        original_path=f"photos_processed/{quiet_client.id}/old.jpg",
        taken_at=datetime.now(timezone.utc) - timedelta(days=8),
        status=ProcessingStatus.PROCESSED,
    )
    recent_photo = Photo(
        client_id=active_client.id,
        filename="recent.jpg",
        original_path=f"photos_processed/{active_client.id}/recent.jpg",
        taken_at=datetime.now(timezone.utc) - timedelta(days=1),
        status=ProcessingStatus.PROCESSED,
    )
    db_session.add_all([old_photo, recent_photo])
    db_session.commit()

    response = client.get("/api/dashboard/coach-summary")
    assert response.status_code == 200
    names = {entry["client_name"] for entry in response.json()["needs_attention"]}
    assert "Quiet Client" in names
    assert "Never Active" in names
    assert "Active Client" not in names


def test_coach_summary_week_stats_counts_recent_activity(client, db_session):
    user = _login(client, db_session)
    c1 = Client(owner_id=user.id, name="Client A")
    c2 = Client(owner_id=user.id, name="Client B")
    db_session.add_all([c1, c2])
    db_session.commit()
    db_session.refresh(c1)
    db_session.refresh(c2)

    recent_checkin = CheckinSubmission(
        client_id=c1.id,
        weight_kg=80.0,
        status=CheckinStatus.PENDING,
        submitted_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    old_checkin = CheckinSubmission(
        client_id=c1.id,
        weight_kg=79.0,
        status=CheckinStatus.REVIEWED,
        submitted_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    recent_photo = Photo(
        client_id=c2.id,
        filename="recent.jpg",
        original_path=f"photos_processed/{c2.id}/recent.jpg",
        taken_at=datetime.now(timezone.utc) - timedelta(days=3),
        status=ProcessingStatus.PROCESSED,
    )
    db_session.add_all([recent_checkin, old_checkin, recent_photo])
    db_session.commit()

    response = client.get("/api/dashboard/coach-summary")
    assert response.status_code == 200
    week_stats = response.json()["week_stats"]
    assert week_stats["checkins"] == 1
    assert week_stats["photos"] == 1
    assert week_stats["active_clients"] == 2


def test_coach_summary_scoped_to_own_clients_only(client, db_session):
    _login(client, db_session, email="coach1@b.com")
    client.post("/api/auth/logout")
    other = _login(client, db_session, email="coach2@b.com")
    other_client = Client(owner_id=other.id, name="Other Coach Client")
    db_session.add(other_client)
    db_session.commit()
    db_session.refresh(other_client)

    old_checkin = CheckinSubmission(
        client_id=other_client.id,
        weight_kg=80.0,
        status=CheckinStatus.PENDING,
        submitted_at=datetime.now(timezone.utc),
    )
    db_session.add(old_checkin)
    db_session.commit()

    client.post("/api/auth/logout")
    _login(client, db_session, email="coach1@b.com")
    response = client.get("/api/dashboard/coach-summary")
    assert response.status_code == 200
    assert response.json()["pending_checkins"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_dashboard_router.py -v`
Expected: FAIL with 404 (endpoint doesn't exist yet).

- [ ] **Step 3: Create the response schema**

Create `backend/app/schemas/dashboard.py`:

```python
"""Response-Schema für das Coach-Dashboard-Widget-Layout - siehe
Design-Spec "Coach-Dashboard: 4-Widget-Layout"."""
from datetime import datetime

from pydantic import BaseModel


class PendingCheckinSummary(BaseModel):
    id: int
    client_id: int
    client_name: str
    submitted_at: datetime
    weight_kg: float | None


class NeedsAttentionClient(BaseModel):
    client_id: int
    client_name: str
    days_since_activity: int | None  # None = noch nie Aktivität


class WeekStats(BaseModel):
    checkins: int
    photos: int
    active_clients: int


class CoachDashboardSummary(BaseModel):
    pending_checkins: list[PendingCheckinSummary]
    needs_attention: list[NeedsAttentionClient]
    week_stats: WeekStats
```

- [ ] **Step 4: Create the router**

Create `backend/app/routers/dashboard.py`:

```python
"""Aggregierte Kennzahlen fürs Coach-Dashboard-Widget-Layout - siehe
Design-Spec "Coach-Dashboard: 4-Widget-Layout". Nur auf die eigenen
Klienten des eingeloggten Accounts gescoped (analog zu jedem anderen
Router hier), keine gesonderte account_type-Sperre nötig - für
Single-Accounts liefert der Endpunkt einfach triviale/leere Listen.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.checkin_submission import CheckinStatus, CheckinSubmission
from app.models.client import Client
from app.models.photo import Photo
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.dashboard import (
    CoachDashboardSummary,
    NeedsAttentionClient,
    PendingCheckinSummary,
    WeekStats,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

NEEDS_ATTENTION_THRESHOLD_DAYS = 7


@router.get("/coach-summary", response_model=CoachDashboardSummary)
def coach_summary(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    clients = db.query(Client).filter(Client.owner_id == current_user.id).all()
    client_ids = [c.id for c in clients]
    client_names = {c.id: c.name for c in clients}

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    # --- pending_checkins ---
    pending_rows = (
        db.query(CheckinSubmission)
        .filter(
            CheckinSubmission.client_id.in_(client_ids),
            CheckinSubmission.status == CheckinStatus.PENDING,
        )
        .order_by(CheckinSubmission.submitted_at.desc())
        .all()
    )
    pending_checkins = [
        PendingCheckinSummary(
            id=row.id,
            client_id=row.client_id,
            client_name=client_names[row.client_id],
            submitted_at=row.submitted_at,
            weight_kg=row.weight_kg,
        )
        for row in pending_rows
    ]

    # --- needs_attention: letzte Aktivität = neuestes Foto ODER neuester
    # Check-in je Klient (kombiniert, nicht nur Fotos - siehe Design-Spec).
    last_photo = dict(
        db.query(Photo.client_id, func.max(Photo.taken_at))
        .filter(Photo.client_id.in_(client_ids))
        .group_by(Photo.client_id)
        .all()
    )
    last_checkin = dict(
        db.query(CheckinSubmission.client_id, func.max(CheckinSubmission.submitted_at))
        .filter(CheckinSubmission.client_id.in_(client_ids))
        .group_by(CheckinSubmission.client_id)
        .all()
    )

    needs_attention = []
    for c in clients:
        candidates = [d for d in (last_photo.get(c.id), last_checkin.get(c.id)) if d is not None]
        last_activity_dt = max(candidates) if candidates else None
        if last_activity_dt is not None and last_activity_dt.tzinfo is None:
            last_activity_dt = last_activity_dt.replace(tzinfo=timezone.utc)

        if last_activity_dt is None:
            needs_attention.append(NeedsAttentionClient(
                client_id=c.id, client_name=c.name, days_since_activity=None
            ))
        elif last_activity_dt < now - timedelta(days=NEEDS_ATTENTION_THRESHOLD_DAYS):
            days = (now - last_activity_dt).days
            needs_attention.append(NeedsAttentionClient(
                client_id=c.id, client_name=c.name, days_since_activity=days
            ))
    # None ("nie aktiv") zuerst, danach absteigend nach days_since_activity.
    needs_attention.sort(
        key=lambda entry: (entry.days_since_activity is not None, -(entry.days_since_activity or 0))
    )

    # --- week_stats ---
    checkins_this_week = (
        db.query(func.count(CheckinSubmission.id))
        .filter(
            CheckinSubmission.client_id.in_(client_ids),
            CheckinSubmission.submitted_at >= week_ago,
        )
        .scalar()
        or 0
    )
    photos_this_week = (
        db.query(func.count(Photo.id))
        .filter(Photo.client_id.in_(client_ids), Photo.taken_at >= week_ago)
        .scalar()
        or 0
    )
    active_client_ids = set(
        cid
        for (cid,) in db.query(CheckinSubmission.client_id)
        .filter(
            CheckinSubmission.client_id.in_(client_ids),
            CheckinSubmission.submitted_at >= week_ago,
        )
        .distinct()
        .all()
    ) | set(
        cid
        for (cid,) in db.query(Photo.client_id)
        .filter(Photo.client_id.in_(client_ids), Photo.taken_at >= week_ago)
        .distinct()
        .all()
    )

    return CoachDashboardSummary(
        pending_checkins=pending_checkins,
        needs_attention=needs_attention,
        week_stats=WeekStats(
            checkins=checkins_this_week,
            photos=photos_this_week,
            active_clients=len(active_client_ids),
        ),
    )
```

- [ ] **Step 5: Register the router**

In `backend/app/main.py`, update the import line (currently):

```python
from app.routers import auth, billing, checkins, clients, comparisons, day_logs, photos, poses, public_checkin, settings as settings_router
```

to:

```python
from app.routers import auth, billing, checkins, clients, comparisons, dashboard, day_logs, photos, poses, public_checkin, settings as settings_router
```

And add this line next to the other `app.include_router(...)` calls (after `app.include_router(clients.router)`):

```python
app.include_router(dashboard.router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_dashboard_router.py -v`
Expected: all PASS.

- [ ] **Step 7: Run the full backend test suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all PASS except the pre-existing unrelated `test_gemini_key_is_scoped_per_account` failure.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/dashboard.py backend/app/routers/dashboard.py backend/app/main.py backend/tests/test_dashboard_router.py
git commit -m "feat: add coach-summary dashboard aggregation endpoint"
```

---

### Task 2: Frontend API client + types

**Files:**
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add types and the API method**

In `frontend/src/api/client.ts`, add these types near the other type definitions (after the `CurrentUser` interface):

```typescript
export interface PendingCheckinSummary {
  id: number;
  client_id: number;
  client_name: string;
  submitted_at: string;
  weight_kg: number | null;
}

export interface NeedsAttentionClient {
  client_id: number;
  client_name: string;
  days_since_activity: number | null;
}

export interface WeekStats {
  checkins: number;
  photos: number;
  active_clients: number;
}

export interface CoachDashboardSummary {
  pending_checkins: PendingCheckinSummary[];
  needs_attention: NeedsAttentionClient[];
  week_stats: WeekStats;
}
```

Add a new `dashboard` namespace to the `api` object (place it next to `billing`, before `auth`):

```typescript
  dashboard: {
    coachSummary: () =>
      client.get<CoachDashboardSummary>("/dashboard/coach-summary").then((r) => r.data),
  },
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat: add coach dashboard summary API client"
```

---

### Task 3: Replace Dashboard.tsx with the 4-widget layout

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: Replace the full file content**

Replace the entire content of `frontend/src/pages/Dashboard.tsx` with:

```tsx
// frontend/src/pages/Dashboard.tsx
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import PageHeader from "../components/PageHeader";
import { Card } from "../components/Card";
import { UpgradeBanner } from "../components/UpgradeBanner";
import { useCurrentUser } from "../hooks/useCurrentUser";
import { useOnboarding } from "../contexts/OnboardingContext";
import type {
  Client,
  CoachDashboardSummary,
  NeedsAttentionClient,
  PendingCheckinSummary,
} from "../types";

export default function Dashboard() {
  const queryClient = useQueryClient();
  const { data: user } = useCurrentUser();
  const { phase, stepIndex, steps, nextStep } = useOnboarding();
  const navigate = useNavigate();
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [heightCm, setHeightCm] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [gender, setGender] = useState("");
  const [startDate, setStartDate] = useState("");

  const clientsQuery = useQuery({ queryKey: ["clients"], queryFn: api.clients.list });
  const summaryQuery = useQuery({
    queryKey: ["dashboard", "coach-summary"],
    queryFn: api.dashboard.coachSummary,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      api.clients.create({
        name,
        height_cm: heightCm.trim() === "" ? null : Number(heightCm),
        birth_date: birthDate.trim() === "" ? null : birthDate,
        gender: gender.trim() === "" ? null : gender,
        start_date: startDate.trim() === "" ? null : startDate,
      }),
    onSuccess: (createdClient) => {
      queryClient.invalidateQueries({ queryKey: ["clients"] });
      setShowForm(false);
      setName("");
      setHeightCm("");
      setBirthDate("");
      setGender("");
      setStartDate("");

      if (phase === "tour" && steps[stepIndex]?.id === "new-client") {
        nextStep();
        navigate(`/clients/${createdClient.id}/settings`);
      }
    },
  });

  const clients = clientsQuery.data ?? [];

  return (
    <div>
      <PageHeader
        title="My Clients"
        actions={
          <button
            data-tour="dashboard-new-client"
            onClick={() => setShowForm((s) => !s)}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90"
          >
            Add New Client
          </button>
        }
      />

      {user?.account_type === "coach" &&
        !["trialing", "active"].includes(user.subscription_status ?? "") &&
        clients.length >= 1 && (
          <div className="mb-4">
            <UpgradeBanner message="You're already using one client for free — you'll need a subscription for more." />
          </div>
        )}

      {showForm && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim()) createMutation.mutate();
          }}
          className="mb-6 grid grid-cols-1 gap-3 rounded-xl border border-white/5 bg-surface p-4 sm:grid-cols-2"
        >
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Name
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Height (cm)
            <input
              type="number"
              value={heightCm}
              onChange={(e) => setHeightCm(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Date of Birth
            <input
              type="date"
              value={birthDate}
              onChange={(e) => setBirthDate(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Gender
            <input
              value={gender}
              onChange={(e) => setGender(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Start Date
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          {(createMutation.error as any)?.response?.status === 402 && (
            <p className="text-sm text-red-400 sm:col-span-2">
              Client limit reached -{" "}
              <Link to="/account" className="underline">
                subscribe/upgrade
              </Link>
              {" "}to add more clients.
            </p>
          )}
          <div className="flex items-end">
            <button
              type="submit"
              disabled={!name.trim() || createMutation.isPending}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-40"
            >
              {createMutation.isPending ? "Adding…" : "Add"}
            </button>
          </div>
        </form>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <ClientsWidget clients={clients} isLoading={clientsQuery.isLoading} />
        <PendingCheckinsWidget
          items={summaryQuery.data?.pending_checkins ?? []}
          isLoading={summaryQuery.isLoading}
        />
        <NeedsAttentionWidget
          items={summaryQuery.data?.needs_attention ?? []}
          isLoading={summaryQuery.isLoading}
        />
        <WeekStatsWidget stats={summaryQuery.data?.week_stats} isLoading={summaryQuery.isLoading} />
      </div>
    </div>
  );
}

function ClientsWidget({ clients, isLoading }: { clients: Client[]; isLoading: boolean }) {
  const [search, setSearch] = useState("");

  const filtered = useMemo(
    () => clients.filter((c) => c.name.toLowerCase().includes(search.trim().toLowerCase())),
    [clients, search]
  );

  return (
    <Card title="Clients">
      <input
        type="search"
        placeholder="Search clients…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="mb-3 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white focus:border-accent focus:outline-none"
      />
      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {!isLoading && filtered.length === 0 && (
        <p className="text-sm text-slate-500">No clients found.</p>
      )}
      <div className="max-h-64 space-y-1 overflow-y-auto">
        {filtered.map((c) => (
          <Link
            key={c.id}
            to={`/clients/${c.id}/timeline`}
            className="flex items-center justify-between rounded-lg px-2 py-1.5 text-sm text-slate-300 hover:bg-white/5"
          >
            <span>{c.name}</span>
            {c.pending_checkins_count > 0 && (
              <span className="shrink-0 rounded-full bg-amber-500/15 px-2 py-0.5 text-xs font-medium text-amber-400">
                {c.pending_checkins_count} pending
              </span>
            )}
          </Link>
        ))}
      </div>
    </Card>
  );
}

function PendingCheckinsWidget({
  items,
  isLoading,
}: {
  items: PendingCheckinSummary[];
  isLoading: boolean;
}) {
  const queryClient = useQueryClient();

  const markSeenMutation = useMutation({
    mutationFn: (item: PendingCheckinSummary) =>
      api.checkins.update(item.client_id, item.id, { mark_reviewed: true }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["dashboard", "coach-summary"] });
    },
  });

  return (
    <Card title="Unseen check-ins">
      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {!isLoading && items.length === 0 && (
        <p className="text-sm text-slate-500">No pending check-ins.</p>
      )}
      <div className="max-h-64 space-y-2 overflow-y-auto">
        {items.map((item) => (
          <div
            key={item.id}
            className="flex items-center justify-between gap-2 rounded-lg bg-amber-500/5 px-3 py-2"
          >
            <div className="min-w-0">
              <p className="truncate text-sm text-slate-200">{item.client_name}</p>
              <p className="text-xs text-slate-500">
                {new Date(item.submitted_at).toLocaleDateString("en-US")}
                {item.weight_kg != null ? ` · ${item.weight_kg} kg` : ""}
              </p>
            </div>
            <button
              onClick={() => markSeenMutation.mutate(item)}
              disabled={markSeenMutation.isPending}
              className="shrink-0 rounded-lg border border-white/10 px-3 py-1.5 text-xs text-slate-300 hover:bg-white/10 disabled:opacity-50"
            >
              Mark seen
            </button>
          </div>
        ))}
      </div>
    </Card>
  );
}

function NeedsAttentionWidget({
  items,
  isLoading,
}: {
  items: NeedsAttentionClient[];
  isLoading: boolean;
}) {
  return (
    <Card title="Needs attention">
      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {!isLoading && items.length === 0 && (
        <p className="text-sm text-slate-500">Everyone's on track.</p>
      )}
      <div className="max-h-64 space-y-1 overflow-y-auto">
        {items.map((entry) => (
          <Link
            key={entry.client_id}
            to={`/clients/${entry.client_id}/timeline`}
            className="flex items-center justify-between rounded-lg bg-red-500/5 px-3 py-2 text-sm hover:bg-red-500/10"
          >
            <span className="text-slate-200">{entry.client_name}</span>
            <span className="text-xs text-red-400">
              {entry.days_since_activity === null
                ? "Never active"
                : `${entry.days_since_activity} days quiet`}
            </span>
          </Link>
        ))}
      </div>
    </Card>
  );
}

function WeekStatsWidget({
  stats,
  isLoading,
}: {
  stats: CoachDashboardSummary["week_stats"] | undefined;
  isLoading: boolean;
}) {
  return (
    <Card title="This week">
      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {!isLoading && stats && (
        <div className="grid grid-cols-3 gap-2">
          <div>
            <p className="text-xl font-medium text-accent">{stats.checkins}</p>
            <p className="text-xs text-slate-500">check-ins</p>
          </div>
          <div>
            <p className="text-xl font-medium text-accent">{stats.photos}</p>
            <p className="text-xs text-slate-500">photos</p>
          </div>
          <div>
            <p className="text-xl font-medium text-accent">{stats.active_clients}</p>
            <p className="text-xs text-slate-500">active clients</p>
          </div>
        </div>
      )}
    </Card>
  );
}
```

- [ ] **Step 2: Add the new types to `frontend/src/types/index.ts`**

The types live in `frontend/src/types/index.ts` (a directory with an `index.ts`, NOT a flat `types.ts` file) as direct interface definitions - e.g. `export interface Client { ... }`, `export interface Photo { ... }`. Add these three new interfaces at the end of `frontend/src/types/index.ts`, matching that exact pattern:

```typescript
export interface PendingCheckinSummary {
  id: number;
  client_id: number;
  client_name: string;
  submitted_at: string;
  weight_kg: number | null;
}

export interface NeedsAttentionClient {
  client_id: number;
  client_name: string;
  days_since_activity: number | null;
}

export interface WeekStats {
  checkins: number;
  photos: number;
  active_clients: number;
}

export interface CoachDashboardSummary {
  pending_checkins: PendingCheckinSummary[];
  needs_attention: NeedsAttentionClient[];
  week_stats: WeekStats;
}
```

Since these types now live in BOTH `frontend/src/api/client.ts` (added in Task 2) AND `frontend/src/types/index.ts`, remove the duplicate definitions from `frontend/src/api/client.ts` (added in Task 2, Step 1) and instead import them there from `../types` - check how other types shared between the two files are handled (e.g. how `Client`, `Photo`, `Pose` are imported into `client.ts` at its top, per its existing `import type { CheckinSubmission, Client, DayLog, Photo, Pose, PublicCheckinPage, UnprocessedPhoto } from "../types";` line) and add `CoachDashboardSummary`, `NeedsAttentionClient`, `PendingCheckinSummary`, `WeekStats` to that same import line instead of leaving the standalone `export interface` copies from Task 2 in place.

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Manual verification**

Read through the rewritten `Dashboard.tsx` and confirm:
- The "Add New Client" flow (button, inline form, mutation, onboarding-tour hook) is unchanged from before.
- All 4 widgets are present in a `grid-cols-1 md:grid-cols-2` container.
- No leftover references to `DashboardClientCard`, `ageFromBirthDate`, `availableGenders`, `genderFilter`, or `EmptyState`/`SkeletonGrid` imports that are no longer used (the old full-grid view and its gender filter are gone per the design spec - YAGNI).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx frontend/src/types.ts
git commit -m "feat: replace coach dashboard client grid with 4-widget layout"
```

---

### Task 4: Holistic review + finish branch

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all PASS except the pre-existing, unrelated `test_gemini_key_is_scoped_per_account` failure.

- [ ] **Step 2: Run frontend type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Manual review checklist**

- Confirm `needs_attention` computation in `backend/app/routers/dashboard.py` uses BOTH photo `taken_at` AND checkin `submitted_at` (not just the pre-existing photo-only `last_activity` field on `ClientOut`) - this is a deliberate deviation from a literal "reuse `last_activity`" reading of the spec, made because the spec's own wording defines "activity" as "Foto/Check-in" combined. Confirm the tests in Task 1 actually exercise both photo-only and checkin-only quiet/active cases.
- Confirm `PendingCheckinsWidget`'s "Mark seen" button calls `api.checkins.update` with the exact signature already used elsewhere in the app (check `frontend/src/pages/ClientCheckins.tsx` or wherever `mark_reviewed` is currently called, to confirm parameter order/shape matches).
- No leftover German user-facing strings.

- [ ] **Step 4: Use the finishing-a-development-branch skill**

Invoke `superpowers:finishing-a-development-branch` to push per the user's standing "option 1" preference (this session works directly on `dev`).
