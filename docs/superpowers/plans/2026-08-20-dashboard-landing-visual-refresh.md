# Dashboard & Landing Visual Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the coach Dashboard feel alive and professional (greeting, sparklines, avatars, activity feed, weekly chart, positive empty states) and give the Landing page a real hero visual, using the existing dark theme + accent color (`#22d3ee`, already Richtung A) as-is.

**Architecture:** Backend gets three new read-only fields on the existing `GET /api/dashboard/coach-summary` response (no new endpoint, no new tables — pure aggregation of existing `CheckinSubmission`/`Photo`/`Client` rows). Frontend gets two new small shared components (`Avatar`, `Sparkline`) and two new Dashboard widgets, plus a CSS-only hero mockup on the Landing page (no external image asset needed).

**Tech Stack:** FastAPI + SQLAlchemy + pytest (backend), React + TanStack Query + Tailwind + TypeScript (frontend, verified via `tsc --noEmit`, no frontend test framework exists in this repo).

---

### Task 1: Backend — extend coach-summary with activity feed, 7-day activity, weekly chart

**Files:**
- Modify: `backend/app/schemas/dashboard.py`
- Modify: `backend/app/routers/dashboard.py`
- Test: `backend/tests/test_dashboard_router.py`

- [ ] **Step 1: Add the new response models**

In `backend/app/schemas/dashboard.py`, add these three classes and extend `CoachDashboardSummary`:

```python
class DayCount(BaseModel):
    date: str  # ISO date "YYYY-MM-DD"
    count: int


class WeekCount(BaseModel):
    week_start: str  # ISO date (Monday) "YYYY-MM-DD"
    count: int


class ActivityItem(BaseModel):
    type: str  # "checkin_submitted" | "checkin_reviewed" | "client_added"
    client_id: int
    client_name: str
    timestamp: datetime


class CoachDashboardSummary(BaseModel):
    pending_checkins: list[PendingCheckinSummary]
    needs_attention: list[NeedsAttentionClient]
    week_stats: WeekStats
    active_clients_last_7_days: list[DayCount]
    checkins_per_week: list[WeekCount]
    activity_feed: list[ActivityItem]
```

Replace the existing `class CoachDashboardSummary(BaseModel):` block (currently just `pending_checkins`/`needs_attention`/`week_stats`) with the extended version above.

- [ ] **Step 2: Write the failing tests**

Append to `backend/tests/test_dashboard_router.py`:

```python
def test_coach_summary_activity_feed_sorted_newest_first(client, db_session):
    user = _login(client, db_session)
    old_client = Client(owner_id=user.id, name="Old Client")
    db_session.add(old_client)
    db_session.commit()
    db_session.refresh(old_client)

    old_client.created_at = datetime.now(timezone.utc) - timedelta(days=5)
    checkin = CheckinSubmission(
        client_id=old_client.id,
        weight_kg=80.0,
        status=CheckinStatus.REVIEWED,
        submitted_at=datetime.now(timezone.utc) - timedelta(days=2),
        reviewed_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(checkin)
    db_session.commit()

    response = client.get("/api/dashboard/coach-summary")
    assert response.status_code == 200
    feed = response.json()["activity_feed"]
    assert len(feed) >= 2
    # neuestes Ereignis zuerst
    assert feed[0]["type"] == "checkin_reviewed"
    types = {item["type"] for item in feed}
    assert "checkin_submitted" in types
    assert "client_added" in types


def test_coach_summary_activity_feed_limited_to_five(client, db_session):
    user = _login(client, db_session)
    c = Client(owner_id=user.id, name="Busy Client")
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)

    for i in range(8):
        db_session.add(
            CheckinSubmission(
                client_id=c.id,
                weight_kg=80.0,
                status=CheckinStatus.PENDING,
                submitted_at=datetime.now(timezone.utc) - timedelta(hours=i),
            )
        )
    db_session.commit()

    response = client.get("/api/dashboard/coach-summary")
    assert response.status_code == 200
    assert len(response.json()["activity_feed"]) == 5


def test_coach_summary_active_clients_last_7_days_has_seven_entries(client, db_session):
    user = _login(client, db_session)
    c = Client(owner_id=user.id, name="Client A")
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)

    db_session.add(
        CheckinSubmission(
            client_id=c.id,
            weight_kg=80.0,
            status=CheckinStatus.PENDING,
            submitted_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    response = client.get("/api/dashboard/coach-summary")
    assert response.status_code == 200
    days = response.json()["active_clients_last_7_days"]
    assert len(days) == 7
    # heutiger Tag (letzter Eintrag) hat mindestens 1 aktiven Klienten
    assert days[-1]["count"] >= 1


def test_coach_summary_checkins_per_week_has_six_entries(client, db_session):
    user = _login(client, db_session)
    c = Client(owner_id=user.id, name="Client A")
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)

    db_session.add(
        CheckinSubmission(
            client_id=c.id,
            weight_kg=80.0,
            status=CheckinStatus.PENDING,
            submitted_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    response = client.get("/api/dashboard/coach-summary")
    assert response.status_code == 200
    weeks = response.json()["checkins_per_week"]
    assert len(weeks) == 6
    assert weeks[-1]["count"] >= 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_dashboard_router.py -v`
Expected: the 4 new tests FAIL with `KeyError: 'activity_feed'` (or similar — the fields don't exist on the response yet).

- [ ] **Step 4: Implement the aggregation logic**

In `backend/app/routers/dashboard.py`, update the import line to include the new schemas:

```python
from app.schemas.dashboard import (
    ActivityItem,
    CoachDashboardSummary,
    DayCount,
    NeedsAttentionClient,
    PendingCheckinSummary,
    WeekCount,
    WeekStats,
)
```

Then, inside `coach_summary(...)`, right before the final `return CoachDashboardSummary(...)` statement, insert:

```python
    # --- activity_feed: letzte 5 Ereignisse (Check-in eingereicht/reviewed,
    # neuer Klient), neueste zuerst. Reine Aggregation, kein neues Modell.
    all_checkins = (
        db.query(CheckinSubmission)
        .filter(CheckinSubmission.client_id.in_(client_ids))
        .all()
    )

    def _aware(dt: datetime) -> datetime:
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

    activity_events: list[ActivityItem] = []
    for row in all_checkins:
        activity_events.append(
            ActivityItem(
                type="checkin_submitted",
                client_id=row.client_id,
                client_name=client_names[row.client_id],
                timestamp=row.submitted_at,
            )
        )
        if row.status == CheckinStatus.REVIEWED and row.reviewed_at is not None:
            activity_events.append(
                ActivityItem(
                    type="checkin_reviewed",
                    client_id=row.client_id,
                    client_name=client_names[row.client_id],
                    timestamp=row.reviewed_at,
                )
            )
    for c in clients:
        activity_events.append(
            ActivityItem(
                type="client_added",
                client_id=c.id,
                client_name=c.name,
                timestamp=c.created_at,
            )
        )
    activity_events.sort(key=lambda e: _aware(e.timestamp), reverse=True)
    activity_feed = activity_events[:5]

    # --- active_clients_last_7_days: pro Kalendertag (UTC), wie viele
    # Klienten an dem Tag einen Check-in eingereicht ODER ein Foto
    # aufgenommen haben. Älteste zuerst, heute zuletzt.
    photo_rows_7d = (
        db.query(Photo.client_id, Photo.taken_at)
        .filter(Photo.client_id.in_(client_ids), Photo.taken_at >= now - timedelta(days=7))
        .all()
    )
    active_clients_last_7_days: list[DayCount] = []
    for offset in range(6, -1, -1):
        day_start = (now - timedelta(days=offset)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        day_end = day_start + timedelta(days=1)
        active_ids = {
            row.client_id
            for row in all_checkins
            if day_start <= _aware(row.submitted_at) < day_end
        }
        active_ids |= {
            cid for cid, taken_at in photo_rows_7d if day_start <= _aware(taken_at) < day_end
        }
        active_clients_last_7_days.append(
            DayCount(date=day_start.date().isoformat(), count=len(active_ids))
        )

    # --- checkins_per_week: letzte 6 Kalenderwochen (Montag-Start), Anzahl
    # eingereichter Check-ins über alle Klienten.
    current_week_start = now.date() - timedelta(days=now.weekday())
    checkins_per_week: list[WeekCount] = []
    for weeks_ago in range(5, -1, -1):
        week_start = current_week_start - timedelta(weeks=weeks_ago)
        week_end = week_start + timedelta(days=7)
        count = sum(
            1 for row in all_checkins if week_start <= row.submitted_at.date() < week_end
        )
        checkins_per_week.append(WeekCount(week_start=week_start.isoformat(), count=count))
```

Then update the return statement to include the three new fields:

```python
    return CoachDashboardSummary(
        pending_checkins=pending_checkins,
        needs_attention=needs_attention,
        week_stats=WeekStats(
            checkins=checkins_this_week,
            photos=photos_this_week,
            active_clients=len(active_client_ids),
        ),
        active_clients_last_7_days=active_clients_last_7_days,
        checkins_per_week=checkins_per_week,
        activity_feed=activity_feed,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_dashboard_router.py -v`
Expected: all tests PASS (the 5 pre-existing ones + the 4 new ones = 9 passed).

- [ ] **Step 6: Run the full backend suite to check for regressions**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: same pass count as before this change, plus the 4 new tests (only the pre-existing unrelated `test_gemini_key_is_scoped_per_account` flaky test may fail — that's expected and unrelated).

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/dashboard.py backend/app/routers/dashboard.py backend/tests/test_dashboard_router.py
git commit -m "feat: add activity feed, 7-day activity and weekly chart data to coach dashboard summary"
```

---

### Task 2: Frontend — sync types for the extended dashboard response

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Add the new interfaces and extend `CoachDashboardSummary`**

In `frontend/src/types/index.ts`, replace:

```typescript
export interface CoachDashboardSummary {
  pending_checkins: PendingCheckinSummary[];
  needs_attention: NeedsAttentionClient[];
  week_stats: WeekStats;
}
```

with:

```typescript
export interface DayCount {
  date: string;
  count: number;
}

export interface WeekCount {
  week_start: string;
  count: number;
}

export interface ActivityItem {
  type: "checkin_submitted" | "checkin_reviewed" | "client_added";
  client_id: number;
  client_name: string;
  timestamp: string;
}

export interface CoachDashboardSummary {
  pending_checkins: PendingCheckinSummary[];
  needs_attention: NeedsAttentionClient[];
  week_stats: WeekStats;
  active_clients_last_7_days: DayCount[];
  checkins_per_week: WeekCount[];
  activity_feed: ActivityItem[];
}
```

- [ ] **Step 2: Verify the frontend still type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors (nothing consumes the new fields yet, so nothing can be inconsistent with them).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat: add types for dashboard activity feed and chart data"
```

---

### Task 3: Frontend — shared `Avatar` and `Sparkline` components

**Files:**
- Create: `frontend/src/components/Avatar.tsx`
- Create: `frontend/src/components/Sparkline.tsx`

- [ ] **Step 1: Create the Avatar component**

Write `frontend/src/components/Avatar.tsx`:

```tsx
// frontend/src/components/Avatar.tsx
const AVATAR_COLORS = [
  "bg-cyan-500/20 text-cyan-300",
  "bg-violet-500/20 text-violet-300",
  "bg-amber-500/20 text-amber-300",
  "bg-emerald-500/20 text-emerald-300",
  "bg-pink-500/20 text-pink-300",
  "bg-blue-500/20 text-blue-300",
];

/** Deterministisch aus dem Namen abgeleiteter Farbindex, damit derselbe
 * Klient überall im UI dieselbe Avatar-Farbe hat (keine zufällige Farbe
 * pro Render). */
function colorClassFor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  }
  return AVATAR_COLORS[hash % AVATAR_COLORS.length];
}

function initialsFor(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** Initialen-Avatar für Klienten ohne eigenes Profilbild-Feature - siehe
 * Design-Spec "Dashboard & Landing-Page Visual Refresh" Abschnitt 3. */
export function Avatar({ name, size = 24 }: { name: string; size?: number }) {
  return (
    <div
      className={`flex shrink-0 items-center justify-center rounded-full text-[10px] font-semibold ${colorClassFor(name)}`}
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      {initialsFor(name)}
    </div>
  );
}
```

- [ ] **Step 2: Create the Sparkline component**

Write `frontend/src/components/Sparkline.tsx`:

```tsx
// frontend/src/components/Sparkline.tsx

/** Kleine Balken-Sparkline für Kennzahlen-Widgets - siehe Design-Spec
 * "Dashboard & Landing-Page Visual Refresh" Abschnitt 2. Rein
 * dekorativ/informativ, kein Hover/Tooltip (dafür gibt es die
 * ausführlichen Charts auf der Statistics-Seite). */
export function Sparkline({ values, height = 20 }: { values: number[]; height?: number }) {
  const max = Math.max(1, ...values);
  return (
    <div className="flex items-end gap-[3px]" style={{ height }} aria-hidden="true">
      {values.map((v, i) => {
        const isLast = i === values.length - 1;
        return (
          <div
            key={i}
            className={`w-[6px] rounded-sm ${isLast ? "bg-accent" : "bg-accent/35"}`}
            style={{ height: `${Math.max(8, (v / max) * 100)}%` }}
          />
        );
      })}
    </div>
  );
}
```

- [ ] **Step 3: Verify the frontend type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/Avatar.tsx frontend/src/components/Sparkline.tsx
git commit -m "feat: add Avatar and Sparkline shared components"
```

---

### Task 4: Frontend — Dashboard redesign (greeting, avatars, sparkline, positive empty states, activity feed, weekly chart)

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: Add the greeting header**

In `frontend/src/pages/Dashboard.tsx`, add a helper function near the top of the file (after the imports, before `export default function Dashboard()`):

```tsx
function greetingForHour(hour: number): string {
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}
```

Import `Avatar` and `Sparkline` at the top of the file:

```tsx
import { Avatar } from "../components/Avatar";
import { Sparkline } from "../components/Sparkline";
```

Inside `export default function Dashboard()`, right before the `return (` statement, add:

```tsx
  const greeting = greetingForHour(new Date().getHours());
  const activeClientsCount = summaryQuery.data?.week_stats.active_clients ?? 0;
  const checkinsThisWeek = summaryQuery.data?.week_stats.checkins ?? 0;
```

Replace the existing:

```tsx
      <PageHeader
        title="My Clients"
```

with:

```tsx
      <PageHeader
        title={user ? `${greeting}, ${user.display_name}` : "My Clients"}
        description={
          summaryQuery.data
            ? `${activeClientsCount} active client${activeClientsCount === 1 ? "" : "s"} · ${checkinsThisWeek} check-in${checkinsThisWeek === 1 ? "" : "s"} this week`
            : undefined
        }
```

Check `PageHeader`'s props first — read `frontend/src/components/PageHeader.tsx` to confirm it accepts a `description` prop before making this change; if it only accepts `title`/`actions`, add a `description?: string` prop to `PageHeader` that renders as a `<p className="mt-1 text-sm text-slate-400">{description}</p>` under the title.

- [ ] **Step 2: Add avatars to the Clients and Pending Check-ins widgets**

In `ClientsWidget`, inside the `<Link>` that renders each client row, add an `Avatar` before the name:

```tsx
          <Link
            key={c.id}
            to={`/clients/${c.id}/timeline`}
            className="flex items-center gap-2 justify-between rounded-lg px-2 py-1.5 text-sm text-slate-300 hover:bg-white/5"
          >
            <span className="flex items-center gap-2 min-w-0">
              <Avatar name={c.name} />
              <span className="truncate">{c.name}</span>
            </span>
            {c.pending_checkins_count > 0 && (
              <span className="shrink-0 rounded-full bg-amber-500/15 px-2 py-0.5 text-xs font-medium text-amber-400">
                {c.pending_checkins_count} pending
              </span>
            )}
          </Link>
```

In `PendingCheckinsWidget`, inside the `<Link>` that renders each item, add an `Avatar` before the text block:

```tsx
          <Link
            key={item.id}
            to={`/clients/${item.client_id}/checkins`}
            className="flex items-center gap-2 rounded-lg bg-amber-500/5 px-3 py-2 hover:bg-amber-500/10"
          >
            <Avatar name={item.client_name} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm text-slate-200">{item.client_name}</p>
              <p className="text-xs text-slate-500">
                {new Date(item.submitted_at).toLocaleDateString("en-US")}
                {item.weight_kg != null ? ` · ${item.weight_kg} kg` : ""}
              </p>
            </div>
          </Link>
```

- [ ] **Step 3: Add a positive empty state with a checkmark to Needs Attention**

In `NeedsAttentionWidget`, replace:

```tsx
      {!isLoading && items.length === 0 && (
        <p className="text-sm text-slate-500">Everyone's on track.</p>
      )}
```

with:

```tsx
      {!isLoading && items.length === 0 && (
        <p className="flex items-center gap-1.5 text-sm text-emerald-400">
          <span aria-hidden="true">✓</span> Everyone's on track — no client overdue.
        </p>
      )}
```

- [ ] **Step 4: Add a Sparkline to the active-clients stat**

In `WeekStatsWidget`, the component currently receives `stats: CoachDashboardSummary["week_stats"] | undefined`. Change its signature to also accept the 7-day series:

```tsx
function WeekStatsWidget({
  stats,
  activeClientsLast7Days,
  isLoading,
}: {
  stats: CoachDashboardSummary["week_stats"] | undefined;
  activeClientsLast7Days: number[];
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
            <div className="mt-1">
              <Sparkline values={activeClientsLast7Days} />
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
```

Update the call site to pass the new prop:

```tsx
        <WeekStatsWidget
          stats={summaryQuery.data?.week_stats}
          activeClientsLast7Days={(summaryQuery.data?.active_clients_last_7_days ?? []).map((d) => d.count)}
          isLoading={summaryQuery.isLoading}
        />
```

- [ ] **Step 5: Add the Activity Feed widget**

Add this new component at the end of `frontend/src/pages/Dashboard.tsx` (after `WeekStatsWidget`):

```tsx
function ACTIVITY_LABEL(item: ActivityItem): string {
  switch (item.type) {
    case "checkin_submitted":
      return `${item.client_name} submitted a check-in`;
    case "checkin_reviewed":
      return `Feedback sent to ${item.client_name}`;
    case "client_added":
      return `${item.client_name} was added as a client`;
  }
}

function relativeTime(isoTimestamp: string): string {
  const diffMs = Date.now() - new Date(isoTimestamp).getTime();
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  if (diffHours < 1) return "just now";
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays === 1) return "yesterday";
  return `${diffDays}d ago`;
}

function ActivityFeedWidget({ items, isLoading }: { items: ActivityItem[]; isLoading: boolean }) {
  return (
    <Card title="Recent activity" className="md:col-span-2">
      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {!isLoading && items.length === 0 && (
        <p className="text-sm text-slate-500">Nothing yet — activity will show up here.</p>
      )}
      <div className="space-y-1">
        {items.map((item, i) => (
          <div key={i} className="flex items-center gap-2 border-b border-white/5 py-1.5 last:border-0">
            <Avatar name={item.client_name} />
            <p className="flex-1 text-sm text-slate-300">{ACTIVITY_LABEL(item)}</p>
            <p className="shrink-0 text-xs text-slate-500">{relativeTime(item.timestamp)}</p>
          </div>
        ))}
      </div>
    </Card>
  );
}
```

Import `ActivityItem` at the top of the file (extend the existing `import type { ... } from "../types"` line):

```tsx
import type {
  ActivityItem,
  Client,
  CoachDashboardSummary,
  NeedsAttentionClient,
  PendingCheckinSummary,
} from "../types";
```

- [ ] **Step 6: Add the Weekly Checkins Chart widget**

Add this new component right after `ActivityFeedWidget`:

```tsx
function WeeklyCheckinsChartWidget({
  weeks,
  isLoading,
}: {
  weeks: { week_start: string; count: number }[];
  isLoading: boolean;
}) {
  const max = Math.max(1, ...weeks.map((w) => w.count));
  return (
    <Card title="Check-ins per week" className="md:col-span-2">
      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {!isLoading && (
        <div className="flex h-24 items-end gap-3">
          {weeks.map((w) => (
            <div key={w.week_start} className="flex flex-1 flex-col items-center gap-1">
              <div
                className="w-full rounded-t bg-accent/60"
                style={{ height: `${Math.max(4, (w.count / max) * 100)}%` }}
                title={`${w.count} check-ins`}
              />
              <p className="text-[10px] text-slate-500">
                {new Date(w.week_start).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
              </p>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
```

- [ ] **Step 7: Wire the two new widgets into the grid**

Replace:

```tsx
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
```

with:

```tsx
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
        <WeekStatsWidget
          stats={summaryQuery.data?.week_stats}
          activeClientsLast7Days={(summaryQuery.data?.active_clients_last_7_days ?? []).map((d) => d.count)}
          isLoading={summaryQuery.isLoading}
        />
        <ActivityFeedWidget items={summaryQuery.data?.activity_feed ?? []} isLoading={summaryQuery.isLoading} />
        <WeeklyCheckinsChartWidget
          weeks={summaryQuery.data?.checkins_per_week ?? []}
          isLoading={summaryQuery.isLoading}
        />
      </div>
```

- [ ] **Step 8: Verify the frontend type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors. Fix any prop-mismatch errors that surface (e.g. if `PageHeader` needed the `description` prop added in Step 1).

- [ ] **Step 9: Manual check in the browser**

Run the dev server (`cd frontend && npm run dev`, or use the project's existing dev workflow) and open the coach Dashboard. Verify: greeting shows your display name, avatars appear next to client names, "This week" shows a sparkline, "Recent activity" and "Check-ins per week" widgets render (even if empty, they should show the empty-state text, not crash).

- [ ] **Step 10: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx frontend/src/components/PageHeader.tsx
git commit -m "feat: redesign coach dashboard with greeting, avatars, sparklines, activity feed and weekly chart"
```

---

### Task 5: Frontend — Landing page hero visual

**Files:**
- Create: `frontend/src/components/DashboardPreview.tsx`
- Modify: `frontend/src/pages/Landing.tsx`

- [ ] **Step 1: Create a CSS-only dashboard preview mockup**

This stands in for a real product screenshot (per the design spec, a real screenshot needs the finished Task 4 redesign as its subject and gets swapped in by hand later — this mockup ships now so the hero isn't empty in the meantime). Write `frontend/src/components/DashboardPreview.tsx`:

```tsx
// frontend/src/components/DashboardPreview.tsx

/** Stilisierte, rein CSS-basierte Vorschau des Coach-Dashboards für den
 * Landing-Page-Hero - siehe Design-Spec "Dashboard & Landing-Page Visual
 * Refresh" Abschnitt "Hero-Bereich". Platzhalter bis ein echter
 * Screenshot des fertigen Dashboards existiert (braucht das fertige
 * Redesign aus Task 4 als Motiv). */
export function DashboardPreview() {
  return (
    <div className="mx-auto max-w-sm rounded-xl border border-white/10 bg-surface p-3 shadow-2xl shadow-black/40">
      <div className="mb-3 flex gap-1.5">
        <div className="h-2 w-2 rounded-full bg-slate-600" />
        <div className="h-2 w-2 rounded-full bg-slate-600" />
        <div className="h-2 w-2 rounded-full bg-slate-600" />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-lg bg-black/30 p-2">
          <div className="mb-1 h-1.5 w-8 rounded bg-slate-600" />
          <div className="text-lg font-semibold text-accent">4</div>
          <div className="mt-1 flex h-4 items-end gap-[2px]">
            {[40, 70, 55, 90].map((h, i) => (
              <div key={i} className="w-1 rounded-sm bg-accent/50" style={{ height: `${h}%` }} />
            ))}
          </div>
        </div>
        <div className="rounded-lg bg-black/30 p-2">
          <div className="mb-1 h-1.5 w-10 rounded bg-slate-600" />
          <div className="text-lg font-semibold text-accent">2</div>
        </div>
      </div>
      <div className="mt-2 rounded-lg bg-black/30 p-2">
        <div className="mb-1.5 h-1.5 w-14 rounded bg-slate-600" />
        <div className="flex items-center gap-1.5 py-1">
          <div className="h-4 w-4 rounded-full bg-cyan-500/30" />
          <div className="h-1.5 flex-1 rounded bg-slate-700" />
        </div>
        <div className="flex items-center gap-1.5 py-1">
          <div className="h-4 w-4 rounded-full bg-violet-500/30" />
          <div className="h-1.5 flex-1 rounded bg-slate-700" />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Place it in the hero section**

In `frontend/src/pages/Landing.tsx`, import the component:

```tsx
import { DashboardPreview } from "../components/DashboardPreview";
```

Add `<DashboardPreview />` right after the buttons `<div>` and before the closing `</section>` of the hero:

```tsx
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Link
            to="/signup"
            className="rounded-lg bg-accent px-6 py-3 text-sm font-semibold text-slate-900 transition-opacity hover:opacity-90"
          >
            Start as a coach
          </Link>
          <Link
            to="/signup"
            className="rounded-lg border border-white/15 px-6 py-3 text-sm font-semibold text-white transition-colors hover:bg-white/5"
          >
            Track yourself
          </Link>
        </div>

        <div className="mt-12">
          <DashboardPreview />
        </div>
      </section>
```

- [ ] **Step 3: Verify the frontend type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Manual check in the browser**

Open `/` while logged out. Verify the hero section now shows the dashboard preview mockup below the CTA buttons, and it doesn't break the mobile layout (check at a narrow viewport width).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/DashboardPreview.tsx frontend/src/pages/Landing.tsx
git commit -m "feat: add dashboard preview mockup to landing page hero"
```

---

### Task 6: Final review and finish

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all tests pass except the pre-existing unrelated flaky `test_gemini_key_is_scoped_per_account`.

- [ ] **Step 2: Run the full frontend type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Use superpowers:finishing-a-development-branch**

Follow that skill to present merge/PR/keep/discard options and complete the branch.
