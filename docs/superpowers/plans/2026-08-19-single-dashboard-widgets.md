# Single Dashboard Widgets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give single-user accounts a 4-widget dashboard (weight trend with range toggle, recent entries, progress, quick actions) as their new landing page, replacing the direct-to-Timeline redirect.

**Architecture:** New page `SingleDashboard.tsx` under the existing `ClientShell` route nesting, reading only from the already-existing `GET /clients/:id/day-logs` endpoint - no backend changes. `ClientRedirect` and `ClientShell`'s nav get small updates to route single accounts here first.

**Tech Stack:** React, TypeScript, react-router-dom, TanStack Query, lucide-react.

---

### Task 1: Add the `dashboard` route and nav entry

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/ClientRedirect.tsx`
- Modify: `frontend/src/components/ClientShell.tsx`
- Create: `frontend/src/pages/SingleDashboard.tsx` (placeholder in this task, filled in fully in Task 2)

- [ ] **Step 1: Create a minimal placeholder page**

Create `frontend/src/pages/SingleDashboard.tsx` with a minimal placeholder (this task only wires up routing/nav; Task 2 replaces this with the real 4-widget content):

```tsx
// frontend/src/pages/SingleDashboard.tsx
import PageHeader from "../components/PageHeader";

export default function SingleDashboard() {
  return (
    <div>
      <PageHeader title="Dashboard" />
    </div>
  );
}
```

- [ ] **Step 2: Register the route**

In `frontend/src/App.tsx`, add the import near the other page imports (alongside `import Timeline from "./pages/Timeline";` or similar - check the existing import block for the exact insertion point and follow the same style):

```tsx
import SingleDashboard from "./pages/SingleDashboard";
```

In the nested routes under `<Route path="clients/:clientId" element={<ClientShell />}>`, add the new route as the FIRST child, before `timeline`:

```tsx
          <Route path="clients/:clientId" element={<ClientShell />}>
            <Route path="dashboard" element={<SingleDashboard />} />
            <Route path="timeline" element={<Timeline />} />
```

- [ ] **Step 3: Point single-account redirects at the new dashboard**

In `frontend/src/components/ClientRedirect.tsx`, change:

```tsx
  return <Navigate to={`/clients/${firstClient.id}/timeline`} replace />;
```

to:

```tsx
  return <Navigate to={`/clients/${firstClient.id}/dashboard`} replace />;
```

- [ ] **Step 4: Add the nav entry**

In `frontend/src/components/ClientShell.tsx`:

Add `LayoutDashboard` to the existing lucide-react import (currently `import { Menu, Calendar, ListChecks, Upload, GitCompare, BarChart3, Settings, type LucideIcon } from "lucide-react";` - add `LayoutDashboard` to that list).

Add a new first entry to `NAV_ITEMS`:

```tsx
const NAV_ITEMS: NavItem[] = [
  { to: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "timeline", label: "Timeline", icon: Calendar },
  { to: "checkins", label: "Check-ins", icon: ListChecks },
  { to: "unprocessed", label: "Import", icon: Upload },
  { to: "compare", label: "Compare", icon: GitCompare, startsNewGroup: true },
  { to: "statistics", label: "Statistics", icon: BarChart3 },
  { to: "settings", label: "Settings", icon: Settings, startsNewGroup: true },
];
```

Find the existing filter (currently):

```tsx
  const visibleNavItems = NAV_ITEMS.filter(
    (item) => item.to !== "checkins" || user?.account_type === "coach"
  );
```

Replace it with a version that ALSO hides "dashboard" for coach accounts (coaches have their own separate `/dashboard` route outside the client context, not this per-client one):

```tsx
  const visibleNavItems = NAV_ITEMS.filter((item) => {
    if (item.to === "checkins") return user?.account_type === "coach";
    if (item.to === "dashboard") return user?.account_type === "single";
    return true;
  });
```

- [ ] **Step 5: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Manual verification**

Confirm by reading the files: the new "Dashboard" nav item appears first in `NAV_ITEMS`, `visibleNavItems` correctly hides it for coach accounts and hides "checkins" for single accounts (both conditions independent, not mutually exclusive), and `ClientRedirect` now points single accounts at `/clients/:id/dashboard`.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/ClientRedirect.tsx frontend/src/components/ClientShell.tsx frontend/src/pages/SingleDashboard.tsx
git commit -m "feat: add single-user dashboard route and nav entry"
```

---

### Task 2: Build the 4 widgets

**Files:**
- Modify: `frontend/src/pages/SingleDashboard.tsx` (full rewrite of the placeholder from Task 1)

- [ ] **Step 1: Replace the placeholder with the full implementation**

Replace the entire content of `frontend/src/pages/SingleDashboard.tsx` with:

```tsx
// frontend/src/pages/SingleDashboard.tsx
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import PageHeader from "../components/PageHeader";
import { Card } from "../components/Card";

type RangeKey = "1m" | "3m" | "6m" | "1y" | "all";

const RANGE_OPTIONS: { key: RangeKey; label: string; days: number | null }[] = [
  { key: "1m", label: "1 Month", days: 30 },
  { key: "3m", label: "3 Months", days: 90 },
  { key: "6m", label: "6 Months", days: 182 },
  { key: "1y", label: "1 Year", days: 365 },
  { key: "all", label: "All", days: null },
];

export default function SingleDashboard() {
  const { clientId } = useParams<{ clientId: string }>();
  const clientIdNum = Number(clientId);

  const dayLogsQuery = useQuery({
    queryKey: ["day-logs", clientIdNum],
    queryFn: () => api.dayLogs.list(clientIdNum),
    enabled: !!clientId,
  });

  const weighedPoints = useMemo(() => {
    return (dayLogsQuery.data ?? [])
      .filter((d) => d.weight_kg != null)
      .map((d) => ({ date: d.date, weight: d.weight_kg as number }))
      .sort((a, b) => (a.date < b.date ? -1 : 1));
  }, [dayLogsQuery.data]);

  return (
    <div>
      <PageHeader title="Dashboard" />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <WeightTrendWidget points={weighedPoints} isLoading={dayLogsQuery.isLoading} />
        <RecentEntriesWidget points={weighedPoints} isLoading={dayLogsQuery.isLoading} />
        <ProgressWidget points={weighedPoints} isLoading={dayLogsQuery.isLoading} />
        <QuickActionsWidget clientId={clientIdNum} />
      </div>
    </div>
  );
}

function WeightTrendWidget({
  points,
  isLoading,
}: {
  points: { date: string; weight: number }[];
  isLoading: boolean;
}) {
  const [range, setRange] = useState<RangeKey>("3m");

  const filtered = useMemo(() => {
    const days = RANGE_OPTIONS.find((r) => r.key === range)?.days ?? null;
    if (days == null || points.length === 0) return points;
    const latest = new Date(points[points.length - 1].date);
    const cutoff = new Date(latest);
    cutoff.setDate(cutoff.getDate() - days);
    const cutoffIso = cutoff.toISOString().slice(0, 10);
    return points.filter((p) => p.date >= cutoffIso);
  }, [points, range]);

  return (
    <Card title="Weight trend">
      <div className="mb-3 flex flex-wrap gap-1">
        {RANGE_OPTIONS.map((opt) => (
          <button
            key={opt.key}
            onClick={() => setRange(opt.key)}
            className={`rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
              range === opt.key
                ? "bg-accent text-slate-900"
                : "bg-black/30 text-slate-400 hover:text-white"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {!isLoading && filtered.length < 2 && (
        <p className="text-sm text-slate-500">Not enough data yet.</p>
      )}
      {!isLoading && filtered.length >= 2 && <WeightSparkline points={filtered} />}
    </Card>
  );
}

function WeightSparkline({ points }: { points: { date: string; weight: number }[] }) {
  const width = 300;
  const height = 60;
  const weights = points.map((p) => p.weight);
  const minWeight = Math.min(...weights);
  const maxWeight = Math.max(...weights);
  const range = maxWeight - minWeight || 1;

  const coords = points.map((p, i) => {
    const x = (i / (points.length - 1)) * width;
    const y = height - ((p.weight - minWeight) / range) * height;
    return `${x},${y}`;
  });

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-16 w-full">
      <polyline points={coords.join(" ")} fill="none" stroke="#22d3ee" strokeWidth="2" />
    </svg>
  );
}

function RecentEntriesWidget({
  points,
  isLoading,
}: {
  points: { date: string; weight: number }[];
  isLoading: boolean;
}) {
  const recent = [...points].reverse().slice(0, 5);

  return (
    <Card title="Recent entries">
      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {!isLoading && recent.length === 0 && (
        <p className="text-sm text-slate-500">No weight entries yet.</p>
      )}
      <div className="max-h-64 space-y-1 overflow-y-auto">
        {recent.map((entry) => (
          <div
            key={entry.date}
            className="flex items-center justify-between rounded-lg px-2 py-1.5 text-sm text-slate-300"
          >
            <span>{new Date(entry.date).toLocaleDateString("en-US")}</span>
            <span className="text-slate-400">{entry.weight} kg</span>
          </div>
        ))}
      </div>
    </Card>
  );
}

function ProgressWidget({
  points,
  isLoading,
}: {
  points: { date: string; weight: number }[];
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <Card title="Progress">
        <p className="text-sm text-slate-500">Loading…</p>
      </Card>
    );
  }
  if (points.length === 0) {
    return (
      <Card title="Progress">
        <p className="text-sm text-slate-500">No weight entries yet.</p>
      </Card>
    );
  }

  const first = points[0];
  const last = points[points.length - 1];
  const delta = last.weight - first.weight;
  const max = Math.max(...points.map((p) => p.weight));

  return (
    <Card title="Progress">
      <div className="grid grid-cols-3 gap-2">
        <div>
          <p className="text-xl font-medium text-accent">{last.weight.toFixed(1)}</p>
          <p className="text-xs text-slate-500">current kg</p>
        </div>
        <div>
          <p className="text-xl font-medium text-accent">
            {delta > 0 ? "+" : ""}
            {delta.toFixed(1)}
          </p>
          <p className="text-xs text-slate-500">since start</p>
        </div>
        <div>
          <p className="text-xl font-medium text-accent">{max.toFixed(1)}</p>
          <p className="text-xs text-slate-500">max kg</p>
        </div>
      </div>
    </Card>
  );
}

function QuickActionsWidget({ clientId }: { clientId: number }) {
  return (
    <Card title="Quick actions">
      <div className="flex flex-col gap-2">
        <Link
          to={`/clients/${clientId}/unprocessed`}
          className="rounded-lg border border-white/10 px-4 py-2 text-sm font-medium text-white hover:bg-white/5"
        >
          Upload photos
        </Link>
        <Link
          to={`/clients/${clientId}/compare`}
          className="rounded-lg border border-white/10 px-4 py-2 text-sm font-medium text-white hover:bg-white/5"
        >
          Compare
        </Link>
      </div>
    </Card>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Manual verification**

Read through the file and confirm:
- `WeightTrendWidget`'s range buttons match the same 5 options/labels/day-cutoffs as `Statistics.tsx`'s `RANGE_OPTIONS` (1 Month/3 Months/6 Months/1 Year/All with 30/90/182/365/null days).
- `ProgressWidget` shows "No weight entries yet." instead of crashing when `points` is empty (guards against `Math.max(...[])` returning `-Infinity` and `points[0]`/`points[points.length-1]` being `undefined`).
- `WeightSparkline` is only rendered when there are at least 2 points (avoids division by zero in the x-coordinate calculation, `points.length - 1` would be 0 with a single point).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/SingleDashboard.tsx
git commit -m "feat: build single-user dashboard widgets (weight trend, recent entries, progress, quick actions)"
```

---

### Task 3: Holistic review + finish branch

- [ ] **Step 1: Run frontend type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 2: Manual review checklist**

- Confirm a coach account's per-client nav does NOT show "Dashboard" (only "Checkins" differs between account types before this change - now both "Checkins" and "Dashboard" are conditionally shown, verify neither condition accidentally shows both to the same account type).
- Confirm `ClientRedirect`'s coach branch (`if (user?.account_type === "coach") return <Navigate to="/dashboard" replace />;`) is UNCHANGED - only the single-account branch's target path changed.
- Confirm no leftover German user-facing strings in `SingleDashboard.tsx`.
- Confirm `data-tour` attributes are unaffected (the onboarding tour's `nav-timeline`/`nav-compare`/`nav-checkins` selectors in `OnboardingContext.tsx` still resolve correctly - the new `nav-dashboard` `data-tour` attribute value is new and unused by the tour, which is fine, no tour step references it).

- [ ] **Step 3: Use the finishing-a-development-branch skill**

Invoke `superpowers:finishing-a-development-branch` to push per the user's standing "option 1" preference (this session works directly on `dev`).
