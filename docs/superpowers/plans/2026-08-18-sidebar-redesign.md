# Sidebar Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Visually modernize `ClientShell.tsx`'s vertical navigation - real icons instead of emoji, grouped nav items with dividers, a clearer active state, and a proper header-style collapse toggle - with zero change to routing, data-tour attributes, or coach-only filtering logic.

**Architecture:** Add `lucide-react` as an icon dependency, then rewrite the nav item data structure and both render blocks (desktop sidebar, mobile overlay) in `ClientShell.tsx` to use the new visual treatment. Purely presentational - no new state, no new props, no backend changes.

**Tech Stack:** React, TypeScript, Tailwind CSS, lucide-react (new), react-router-dom (existing).

---

### Task 1: Add lucide-react dependency

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Install the package**

Run:
```bash
cd frontend && npm install lucide-react
```

Expected: `package.json`'s `dependencies` gains a `"lucide-react": "^X.Y.Z"` entry (exact version picked by npm), and `package-lock.json` updates accordingly.

- [ ] **Step 2: Verify it's importable**

Run:
```bash
cd frontend && node -e "console.log(require.resolve('lucide-react'))"
```
Expected: prints a path inside `node_modules/lucide-react` without error.

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore: add lucide-react for sidebar icons"
```

---

### Task 2: Redesign ClientShell.tsx navigation

**Files:**
- Modify: `frontend/src/components/ClientShell.tsx` (entire file rewritten below)

- [ ] **Step 1: Replace the full file content**

Replace the entire content of `frontend/src/components/ClientShell.tsx` with:

```tsx
// frontend/src/components/ClientShell.tsx
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Menu,
  Calendar,
  ListChecks,
  Upload,
  GitCompare,
  BarChart3,
  Settings,
  type LucideIcon,
} from "lucide-react";
import { api } from "../api/client";
import { useCurrentUser } from "../hooks/useCurrentUser";

const SIDEBAR_COLLAPSED_KEY = "bodycomp:sidebarCollapsed";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  // Trennt diesen Punkt optisch von den vorherigen Punkten durch einen
  // Trennstrich - siehe Design-Spec "Sidebar-Redesign" Abschnitt
  // "Gruppierung". Erster Punkt jeder Gruppe außer der allerersten
  // bekommt startsNewGroup=true.
  startsNewGroup?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: "timeline", label: "Timeline", icon: Calendar },
  { to: "checkins", label: "Check-ins", icon: ListChecks },
  { to: "unprocessed", label: "Import", icon: Upload },
  { to: "compare", label: "Compare", icon: GitCompare, startsNewGroup: true },
  { to: "statistics", label: "Statistics", icon: BarChart3 },
  { to: "settings", label: "Settings", icon: Settings, startsNewGroup: true },
];

/** Nur aktiv innerhalb /clients/:clientId/* - fügt die vertikale
 * Kunden-Navi + Mini-Header (aktueller Kundenname) hinzu, siehe
 * Design-Spec Abschnitt "ClientShell (vertikale Kunden-Navi)" und
 * "Sidebar-Redesign" für die visuelle Aufbereitung (Icons, Gruppierung,
 * Toggle-Kopfzeile). */
export default function ClientShell() {
  const { clientId } = useParams<{ clientId: string }>();
  const { data: user } = useCurrentUser();
  // Check-ins ist eine Coach<->Klient-Beziehungsfunktion - bei Single-
  // Accounts (die sich selbst tracken) ergibt der Tab keinen Sinn, siehe
  // Design-Spec "Usability-Fixes Runde 2" Abschnitt 1. Reine
  // Sichtbarkeits-Filterung, keine Datenlöschung - wechselt ein Account
  // später zum Coach, taucht der Tab sofort wieder auf.
  const visibleNavItems = NAV_ITEMS.filter(
    (item) => item.to !== "checkins" || user?.account_type === "coach"
  );
  const location = useLocation();
  const activeNavTo = NAV_ITEMS.find((item) =>
    item.to === "timeline"
      ? location.pathname.endsWith(`/clients/${clientId}/timeline`)
      : location.pathname.includes(`/clients/${clientId}/${item.to}`)
  )?.to;
  const [desktopCollapsed, setDesktopCollapsed] = useState(() => {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true";
  });
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(desktopCollapsed));
  }, [desktopCollapsed]);

  const clientQuery = useQuery({
    // Numerisch, wie in Settings.tsx/ClientCheckins.tsx - sonst sind
    // ["clients", "5"] (string) und ["clients", 5] (number) für React
    // Query zwei getrennte Cache-Einträge, und ein invalidateQueries aus
    // Settings.tsx würde diesen Query hier nie treffen (gefunden im
    // Review von Task 15).
    queryKey: ["clients", Number(clientId)],
    queryFn: () => api.clients.get(Number(clientId)),
    enabled: !!clientId,
  });

  // Aktiver Zustand: 2px Cyan-Balken links + transparenter Cyan-Wash,
  // rechts abgerundet. Inaktiv: transparenter (aber reservierter) Balken,
  // damit beim Zustandswechsel nichts springt - siehe Design-Spec
  // "Sidebar-Redesign" Abschnitt "Aktiver Zustand".
  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-2 rounded-r-lg border-l-2 px-3 py-2 text-sm font-medium transition-colors ${
      isActive
        ? "border-accent bg-accent/10 text-accent"
        : "border-transparent text-slate-400 hover:text-white"
    }`;

  const renderNavItem = (item: NavItem, options: { collapsed?: boolean; onNavigate?: () => void } = {}) => {
    const Icon = item.icon;
    return (
      <div key={item.to}>
        {item.startsNewGroup && (
          <div className="my-1.5 border-t border-white/10" />
        )}
        <NavLink
          to={item.to}
          data-tour={`nav-${item.to}`}
          end={item.to === "timeline"}
          aria-disabled={item.to === activeNavTo}
          onClick={(e) => {
            if (item.to === activeNavTo) {
              e.preventDefault();
              return;
            }
            options.onNavigate?.();
          }}
          className={navLinkClass}
          title={options.collapsed ? item.label : undefined}
        >
          <Icon size={17} aria-hidden="true" />
          {!options.collapsed && item.label}
        </NavLink>
      </div>
    );
  };

  return (
    <div className="flex gap-6">
      {/* Mobile: schmale Leiste mit Toggle, Overlay beim Ausklappen */}
      <button
        onClick={() => setMobileOpen(true)}
        className="fixed left-0 top-16 z-20 rounded-r-lg border border-l-0 border-white/10 bg-surface px-2 py-3 text-slate-400 sm:hidden"
        aria-label="Open navigation"
      >
        <Menu size={18} aria-hidden="true" />
      </button>
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 sm:hidden"
          onClick={() => setMobileOpen(false)}
        >
          <nav
            className="flex h-full w-56 flex-col gap-1 bg-surface p-4"
            onClick={(e) => e.stopPropagation()}
          >
            {visibleNavItems.map((item) =>
              renderNavItem(item, { onNavigate: () => setMobileOpen(false) })
            )}
          </nav>
        </div>
      )}

      {/* Desktop: feste Sidebar, einklappbar - Toggle sitzt als eigene
          Kopfzeile ÜBER den Nav-Punkten (Design-Spec "Toggle-Kopfzeile"),
          statt isoliert unten zu hängen. */}
      <nav
        className={`hidden shrink-0 flex-col gap-1 rounded-xl bg-surface/40 p-2 sm:flex ${
          desktopCollapsed ? "w-14" : "w-48"
        } transition-all`}
      >
        <button
          onClick={() => setDesktopCollapsed((c) => !c)}
          className="flex items-center gap-2 rounded-lg px-3 py-2 text-slate-400 hover:text-white"
          aria-label={desktopCollapsed ? "Expand navigation" : "Collapse navigation"}
        >
          <Menu size={17} aria-hidden="true" />
          {!desktopCollapsed && (
            <span className="text-xs font-medium tracking-wide">Navigation</span>
          )}
        </button>
        <div className="mb-1 border-t border-white/10" />
        {visibleNavItems.map((item) => renderNavItem(item, { collapsed: desktopCollapsed }))}
      </nav>

      <div className="min-w-0 flex-1">
        {clientQuery.data && (
          <div className="mb-4 flex items-center gap-2 rounded-lg bg-surface/60 px-3 py-1.5 text-sm text-slate-300">
            <span className="text-slate-500">Client:</span> {clientQuery.data.name}
          </div>
        )}
        <Outlet />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Manual verification**

Run: `cd frontend && npm run dev` (or use whatever the project's existing local dev-server workflow is), log in as a coach account with at least one client, and confirm:
- Desktop sidebar shows 6 icons (or 5 if viewing as a single account, since Check-ins is hidden), grouped into 3 clusters with visible dividers between Import/Compare and Statistics/Settings.
- Active page's nav item has a cyan left bar, tinted background, and cyan icon/text.
- Clicking the "Navigation" header row (not just the icon) toggles collapsed/expanded state; collapsed state hides all labels including "Navigation" itself, keeping icons centered.
- Collapsed nav items still show a tooltip (native `title` attribute) with the label on hover.
- Resize the browser to mobile width, open the hamburger button (bottom-left fixed button, now a `Menu` icon instead of `☰`), confirm the overlay nav shows the same grouped/icon treatment.
- Reload the page after toggling collapsed - state persists (localStorage).

Stop here and report back once manual verification passes; no automated test suite covers this (it's a presentational-only change per the design spec's testing approach), so this manual pass is the acceptance gate.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ClientShell.tsx
git commit -m "feat: redesign sidebar navigation with icons, grouping, and header toggle"
```

---

### Task 3: Holistic review + finish branch

- [ ] **Step 1: Run frontend type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 2: Manual review checklist**

Re-read `frontend/src/components/ClientShell.tsx` end to end and confirm:
- `data-tour="nav-${item.to}"` attributes are unchanged in content (still `nav-timeline`, `nav-checkins`, etc.) - the onboarding tour's `OnboardingTooltip.tsx`/`OnboardingContext.tsx` selector logic depends on these exact strings and must keep working.
- The `aria-disabled`/`onClick` "already on this page, don't navigate" guard logic is preserved identically to the pre-redesign version (was a subtle behavior, not just styling).
- `visibleNavItems` filtering (coach-only Check-ins) still happens before both the desktop and mobile render paths.
- No leftover unused imports (e.g. if any old emoji-related code was missed).
- No leftover German user-facing strings (English-only app per Stufe 5c).

- [ ] **Step 3: Use the finishing-a-development-branch skill**

Invoke `superpowers:finishing-a-development-branch` to push per the user's standing "option 1" preference (this session works directly on `dev`, not a separate feature branch - "finishing" here means verifying tests/build then pushing `dev` to origin, same pattern as prior features this session).
