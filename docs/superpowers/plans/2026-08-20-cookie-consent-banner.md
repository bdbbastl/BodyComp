# Cookie Consent Banner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bottom-bar cookie consent banner (Accept all / Reject non-essential / Customize with Necessary/Analytics/Marketing toggles) with versioned localStorage persistence and a "Cookie settings" footer link to reopen it, so future non-essential cookies (marketing pixels, cookie-based analytics) have consent infrastructure already in place.

**Architecture:** A single React Context (`CookieConsentContext`) holds the consent decision (persisted to `localStorage`, versioned) and exposes actions + a `hasConsent(category)` helper for future features to call before loading optional scripts. A presentational `CookieConsentBanner` component reads that context and renders the bottom bar; it's mounted once in `App.tsx` alongside the existing `BusyOverlay`/`OnboardingModalGate` pattern so it appears on every route.

**Tech Stack:** React + TypeScript + Tailwind (frontend only, no backend changes). No frontend test framework exists in this repo — verification is via `npx tsc --noEmit` plus a manual browser check, consistent with prior frontend-only tasks in this codebase.

---

### Task 1: `CookieConsentContext` — state, persistence, actions

**Files:**
- Create: `frontend/src/contexts/CookieConsentContext.tsx`

- [ ] **Step 1: Write the context file**

Write `frontend/src/contexts/CookieConsentContext.tsx`:

```tsx
// frontend/src/contexts/CookieConsentContext.tsx
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

export type CookieCategory = "analytics" | "marketing";

interface StoredConsent {
  version: number;
  necessary: true;
  analytics: boolean;
  marketing: boolean;
  decided_at: string;
}

// Erhöhen, wenn sich die Cookie-Policy inhaltlich ändert (z.B. eine neue
// Kategorie kommt dazu) - ältere gespeicherte Einträge mit niedrigerer
// Version gelten dann als "noch nicht entschieden" und das Banner
// erscheint erneut. Siehe Design-Spec "Cookie Consent Banner" Abschnitt
// "Speicherung".
const CONSENT_VERSION = 1;
const STORAGE_KEY = "bodycomp_cookie_consent";

function loadStoredConsent(): StoredConsent | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredConsent;
    if (parsed.version !== CONSENT_VERSION) return null;
    return parsed;
  } catch {
    return null;
  }
}

function saveConsent(consent: StoredConsent) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(consent));
  } catch {
    // localStorage kann in Private-Browsing/mit deaktiviertem Storage
    // fehlschlagen - dann zeigt das Banner beim nächsten Laden einfach
    // erneut an, kein harter Fehler nötig.
  }
}

interface CookieConsentContextValue {
  consent: StoredConsent | null;
  bannerVisible: boolean;
  acceptAll: () => void;
  rejectNonEssential: () => void;
  savePreferences: (prefs: { analytics: boolean; marketing: boolean }) => void;
  openSettings: () => void;
  hasConsent: (category: CookieCategory) => boolean;
}

const CookieConsentContext = createContext<CookieConsentContextValue | null>(null);

/** App-weites Cookie-Consent-Management - siehe Design-Spec "Cookie
 * Consent Banner". Speichert die Entscheidung in localStorage (nicht in
 * einem Cookie - vermeidet das Henne-Ei-Problem, ein Cookie fürs
 * Cookie-Consent selbst zu brauchen). Aktuell ruft noch kein Feature
 * hasConsent() auf (es gibt noch keine nicht-notwendigen Cookies/
 * Scripts), aber der Helper steht für künftige Marketing/Analytics-
 * Integrationen bereit. */
export function CookieConsentProvider({ children }: { children: ReactNode }) {
  const [consent, setConsent] = useState<StoredConsent | null>(loadStoredConsent);
  const [bannerVisible, setBannerVisible] = useState(consent === null);

  const persistAndClose = useCallback((analytics: boolean, marketing: boolean) => {
    const next: StoredConsent = {
      version: CONSENT_VERSION,
      necessary: true,
      analytics,
      marketing,
      decided_at: new Date().toISOString(),
    };
    saveConsent(next);
    setConsent(next);
    setBannerVisible(false);
  }, []);

  const acceptAll = useCallback(() => persistAndClose(true, true), [persistAndClose]);
  const rejectNonEssential = useCallback(() => persistAndClose(false, false), [persistAndClose]);
  const savePreferences = useCallback(
    (prefs: { analytics: boolean; marketing: boolean }) =>
      persistAndClose(prefs.analytics, prefs.marketing),
    [persistAndClose]
  );
  const openSettings = useCallback(() => setBannerVisible(true), []);

  const hasConsent = useCallback(
    (category: CookieCategory) => consent !== null && consent[category] === true,
    [consent]
  );

  const value = useMemo<CookieConsentContextValue>(
    () => ({
      consent,
      bannerVisible,
      acceptAll,
      rejectNonEssential,
      savePreferences,
      openSettings,
      hasConsent,
    }),
    [consent, bannerVisible, acceptAll, rejectNonEssential, savePreferences, openSettings, hasConsent]
  );

  return <CookieConsentContext.Provider value={value}>{children}</CookieConsentContext.Provider>;
}

/** Für Komponenten, die den Consent-Status lesen oder ändern wollen
 * (Banner, Footer-Link, künftige Feature-Gates via hasConsent()). */
export function useCookieConsent(): CookieConsentContextValue {
  const ctx = useContext(CookieConsentContext);
  if (!ctx) throw new Error("useCookieConsent must be used within CookieConsentProvider");
  return ctx;
}
```

- [ ] **Step 2: Verify the frontend type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors (nothing consumes this context yet).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/contexts/CookieConsentContext.tsx
git commit -m "feat: add CookieConsentContext with versioned localStorage persistence"
```

---

### Task 2: `CookieConsentBanner` component

**Files:**
- Create: `frontend/src/components/CookieConsentBanner.tsx`

- [ ] **Step 1: Write the banner component**

Write `frontend/src/components/CookieConsentBanner.tsx`:

```tsx
// frontend/src/components/CookieConsentBanner.tsx
import { useState } from "react";
import { useCookieConsent } from "../contexts/CookieConsentContext";

/** Schmales Consent-Banner am unteren Bildschirmrand - siehe Design-Spec
 * "Cookie Consent Banner" Abschnitt "CookieConsentBanner". Wird einmal in
 * App.tsx eingehängt (analog zu BusyOverlay) und rendert dadurch auf
 * jeder Seite - auch eingeloggte Nutzer müssen entscheiden. */
export function CookieConsentBanner() {
  const { bannerVisible, consent, acceptAll, rejectNonEssential, savePreferences } = useCookieConsent();
  const [customizing, setCustomizing] = useState(false);
  const [analytics, setAnalytics] = useState(consent?.analytics ?? false);
  const [marketing, setMarketing] = useState(consent?.marketing ?? false);

  if (!bannerVisible) return null;

  return (
    <div className="fixed inset-x-0 bottom-0 z-50 border-t border-white/10 bg-surface px-4 py-4 shadow-2xl shadow-black/40 sm:px-6">
      <div className="mx-auto flex max-w-4xl flex-col gap-3">
        <p className="text-sm text-slate-300">
          We use necessary cookies to run this site. With your permission, we'd also like to use
          optional cookies for analytics and marketing - you can change this anytime.
        </p>

        {customizing && (
          <div className="space-y-2 rounded-lg border border-white/10 bg-black/20 p-3">
            <label className="flex items-center justify-between text-sm text-slate-300">
              <span>
                Necessary <span className="text-slate-500">(always on)</span>
              </span>
              <input type="checkbox" checked disabled className="h-4 w-4" />
            </label>
            <label className="flex items-center justify-between text-sm text-slate-300">
              <span>Analytics</span>
              <input
                type="checkbox"
                checked={analytics}
                onChange={(e) => setAnalytics(e.target.checked)}
                className="h-4 w-4"
              />
            </label>
            <label className="flex items-center justify-between text-sm text-slate-300">
              <span>Marketing</span>
              <input
                type="checkbox"
                checked={marketing}
                onChange={(e) => setMarketing(e.target.checked)}
                className="h-4 w-4"
              />
            </label>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          {customizing ? (
            <button
              type="button"
              onClick={() => savePreferences({ analytics, marketing })}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90"
            >
              Save preferences
            </button>
          ) : (
            <>
              <button
                type="button"
                onClick={acceptAll}
                className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90"
              >
                Accept all
              </button>
              <button
                type="button"
                onClick={rejectNonEssential}
                className="rounded-lg border border-white/15 px-4 py-2 text-sm font-medium text-white hover:bg-white/5"
              >
                Reject non-essential
              </button>
              <button
                type="button"
                onClick={() => setCustomizing(true)}
                className="rounded-lg px-4 py-2 text-sm font-medium text-slate-300 hover:text-white"
              >
                Customize
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify the frontend type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/CookieConsentBanner.tsx
git commit -m "feat: add CookieConsentBanner component"
```

---

### Task 3: Wire the provider + banner into the app, add the footer settings link

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/Landing.tsx`

- [ ] **Step 1: Mount the provider and banner in `App.tsx`**

In `frontend/src/App.tsx`, add these imports near the other context/component imports:

```tsx
import { CookieConsentProvider } from "./contexts/CookieConsentContext";
import { CookieConsentBanner } from "./components/CookieConsentBanner";
```

Wrap the existing return value with `CookieConsentProvider` and render `CookieConsentBanner` alongside `BusyOverlay` (same pattern: mounted once, outside `Routes`, so it persists across route changes). Replace:

```tsx
export default function App() {
  return (
    <BusyOverlayProvider>
    <OnboardingProvider>
      <Routes>
```

with:

```tsx
export default function App() {
  return (
    <CookieConsentProvider>
    <BusyOverlayProvider>
    <OnboardingProvider>
      <Routes>
```

And replace the closing tags:

```tsx
    <BusyOverlay />
    </BusyOverlayProvider>
  );
}
```

with:

```tsx
    <BusyOverlay />
    </BusyOverlayProvider>
    <CookieConsentBanner />
    </CookieConsentProvider>
  );
}
```

- [ ] **Step 2: Add the "Cookie settings" footer link on the Landing page**

In `frontend/src/pages/Landing.tsx`, import the hook:

```tsx
import { useCookieConsent } from "../contexts/CookieConsentContext";
```

Inside `export default function Landing()`, right after the existing `const { data: user, isLoading } = useCurrentUser();` line, add:

```tsx
  const { openSettings } = useCookieConsent();
```

Find the footer's link row:

```tsx
          <div className="flex gap-4">
            <Link to="/login" className="hover:text-white">Log in</Link>
            <Link to="/impressum" className="hover:text-white">Legal notice</Link>
            <Link to="/datenschutz" className="hover:text-white">Privacy</Link>
            <Link to="/agb" className="hover:text-white">Terms</Link>
          </div>
```

Replace it with (adds a "Cookie settings" button that reopens the banner):

```tsx
          <div className="flex gap-4">
            <Link to="/login" className="hover:text-white">Log in</Link>
            <Link to="/impressum" className="hover:text-white">Legal notice</Link>
            <Link to="/datenschutz" className="hover:text-white">Privacy</Link>
            <Link to="/agb" className="hover:text-white">Terms</Link>
            <button type="button" onClick={openSettings} className="hover:text-white">
              Cookie settings
            </button>
          </div>
```

- [ ] **Step 3: Verify the frontend type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Manual check in the browser**

Run the dev server and open `/`. Verify: the banner appears at the bottom on first load, "Accept all"/"Reject non-essential" both dismiss it, reloading the page after accepting does NOT show the banner again (localStorage persisted), "Customize" expands the three toggles with Necessary locked on, and the footer's "Cookie settings" link reopens the banner after it was dismissed. Also verify the banner appears on `/login` and other non-Landing pages (it's mounted globally in `App.tsx`, not just on Landing).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/pages/Landing.tsx
git commit -m "feat: mount cookie consent banner app-wide, add footer settings link"
```

---

### Task 4: Final review and finish

- [ ] **Step 1: Run the full frontend type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 2: Run the full backend test suite (sanity check — no backend files touched by this plan)**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: same pass count as before this branch (only the pre-existing unrelated flaky `test_gemini_key_is_scoped_per_account` may fail).

- [ ] **Step 3: Use superpowers:finishing-a-development-branch**

Follow that skill to present merge/PR/keep/discard options and complete the branch.
