# Onboarding-Flow (Stufe 5b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modernes, kurzes Onboarding: Willkommens-Modal (2 Slides) gefolgt von einer kontextuellen Tooltip-Tour, automatisch beim ersten Login und jederzeit über die Account-Seite erneut startbar. Unterschiedlicher Inhalt für Coach- und Single-Accounts. Alle Onboarding-Texte werden direkt auf ENGLISCH geschrieben (siehe Stufe 5c - unnötige Doppelarbeit vermeiden).

**Architecture:** Neues `User.onboarding_completed_at`-Feld + Endpunkt zum Markieren als erledigt. Frontend: `OnboardingContext` (React Context) hält Tour-State, `OnboardingModal`/`OnboardingTooltip`-Komponenten, `data-tour`-Attribute an bestehenden UI-Elementen als Zielpunkte. Reines CSS/Tailwind für Übergänge, keine neue Abhängigkeit.

**Tech Stack:** FastAPI, SQLAlchemy, React, TypeScript, Tailwind CSS.

---

### Task 1: Backend - `onboarding_completed_at`-Feld + Migration

**Files:**
- Modify: `backend/app/models/user.py`
- Modify: `backend/app/core/migrations.py`
- Test: `backend/tests/test_migrations.py`

- [ ] **Step 1: Feld zum User-Model hinzufügen**

In `backend/app/models/user.py`, nach der `free_checkins_used`-Zeile ergänzen:

```python
    # Wann der Onboarding-Flow (Willkommens-Modal + Tooltip-Tour)
    # abgeschlossen oder übersprungen wurde - None = noch nie gesehen,
    # löst beim nächsten Login den automatischen Start aus (siehe
    # Design-Spec "Onboarding-Flow" Abschnitt 2).
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

- [ ] **Step 2: Migration ergänzen**

In `backend/app/core/migrations.py`, `_PENDING_COLUMNS` um eine Zeile ergänzen (ans Ende der Liste):

```python
    ("users", "onboarding_completed_at", "DATETIME"),
```

- [ ] **Step 3: Test schreiben**

In `backend/tests/test_migrations.py` (Struktur der bestehenden Tests dort als Vorbild nehmen - vermutlich ein Test, der eine minimale Legacy-Tabelle ohne die neue Spalte anlegt und prüft, dass `run_lightweight_migrations` sie nachrüstet, ohne zu crashen). Füge einen Test hinzu, der bestätigt, dass eine `users`-Tabelle ohne `onboarding_completed_at`-Spalte nach `run_lightweight_migrations` diese Spalte hat (per `PRAGMA table_info`).

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest -q tests/test_migrations.py`
Expected: alle PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/user.py backend/app/core/migrations.py backend/tests/test_migrations.py
git commit -m "feat: add onboarding_completed_at field to User model"
```

---

### Task 2: Backend - Completion-Endpunkt + `UserOut`-Feld

**Files:**
- Modify: `backend/app/routers/auth.py`
- Modify: `backend/app/schemas/auth.py`
- Test: `backend/tests/test_auth_router.py`

- [ ] **Step 1: `UserOut`-Schema erweitern**

In `backend/app/schemas/auth.py`, nach der `free_checkins_used: int`-Zeile ergänzen:

```python
    onboarding_completed_at: datetime | None
```

- [ ] **Step 2: Endpunkt hinzufügen**

In `backend/app/routers/auth.py`, direkt nach der bestehenden `switch_to_coach`-Funktion (folgt demselben Muster) ergänzen:

```python
@router.patch("/onboarding-complete", response_model=UserOut)
def complete_onboarding(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Markiert den Onboarding-Flow als gesehen (fertig durchlaufen ODER
    übersprungen - beides zählt gleich) - verhindert das automatische
    erneute Auslösen beim nächsten Login. Ein manueller Replay über die
    Account-Seite ruft diesen Endpunkt bewusst NICHT erneut auf, siehe
    Design-Spec "Onboarding-Flow" Abschnitt 2."""
    current_user.onboarding_completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(current_user)
    return current_user
```

Prüfe, ob `datetime`/`timezone` bereits in `auth.py` importiert sind (an mehreren Stellen der Datei bereits verwendet, z.B. für `email_verified_at`) - falls nicht, Import ergänzen.

- [ ] **Step 3: Test schreiben**

In `backend/tests/test_auth_router.py` (Login-Helper-Pattern der Datei als Vorbild nehmen):

```python
def test_complete_onboarding_sets_timestamp(client, db_session):
    _login(client, db_session)  # exakten Helper-Namen/Signatur aus der Datei übernehmen
    response = client.patch("/api/auth/onboarding-complete")
    assert response.status_code == 200
    assert response.json()["onboarding_completed_at"] is not None


def test_complete_onboarding_requires_login(client, db_session):
    response = client.patch("/api/auth/onboarding-complete")
    assert response.status_code == 401
```

(Exakten Namen/Signatur des `_login`-Helpers dieser Testdatei verwenden - unterscheidet sich leicht zwischen Testdateien, siehe andere Tasks in diesem Projekt.)

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest -q tests/test_auth_router.py`
Expected: alle PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/auth.py backend/app/schemas/auth.py backend/tests/test_auth_router.py
git commit -m "feat: add onboarding-complete endpoint"
```

---

### Task 3: Frontend - Types + API-Client

**Files:**
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: `CurrentUser`-Interface erweitern**

In `frontend/src/api/client.ts`, nach `free_checkins_used: number;` ergänzen:

```tsx
  onboarding_completed_at: string | null;
```

- [ ] **Step 2: API-Methode ergänzen**

Im `auth`-Abschnitt von `api`, nach `switchToCoach` ergänzen:

```tsx
    completeOnboarding: () =>
      client.patch<CurrentUser>("/auth/onboarding-complete").then((r) => r.data),
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat: add onboarding types and api client method"
```

---

### Task 4: Frontend - `OnboardingContext`

**Files:**
- Create: `frontend/src/contexts/OnboardingContext.tsx`

- [ ] **Step 1: Steps-Definitionen + Context schreiben**

```tsx
// frontend/src/contexts/OnboardingContext.tsx
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useCurrentUser } from "../hooks/useCurrentUser";

export interface TourStep {
  id: string;
  dataTour: string;
  /** Falls gesetzt, navigiert die Tour dorthin, bevor sie nach dem
   * Ziel-Element sucht (siehe Design-Spec "Onboarding-Flow" Abschnitt 4). */
  route?: (clientId: number) => string;
  title: string;
  body: string;
}

export const COACH_STEPS: TourStep[] = [
  {
    id: "new-client",
    dataTour: "dashboard-new-client",
    title: "Add your first client",
    body: "This is where you add a new client to start tracking their progress.",
  },
  {
    id: "checkin-link",
    dataTour: "settings-checkin-link",
    title: "Share the check-in link",
    body: "Your client uses this link to submit check-ins - no account needed on their side.",
  },
  {
    id: "checkins-nav",
    dataTour: "nav-checkins",
    title: "Review check-ins",
    body: "Submitted check-ins and your feedback show up here.",
  },
];

export const SINGLE_STEPS: TourStep[] = [
  {
    id: "upload",
    dataTour: "unprocessed-upload",
    title: "Upload your first photos",
    body: "Start by uploading your first progress photos here.",
  },
  {
    id: "timeline-nav",
    dataTour: "nav-timeline",
    title: "Your timeline",
    body: "This is where your progress over time shows up.",
  },
  {
    id: "compare-nav",
    dataTour: "nav-compare",
    title: "Compare photos",
    body: "Once you have 2 check-ins, you can compare before/after here.",
  },
];

interface OnboardingContextValue {
  phase: "modal" | "tour" | null;
  modalSlide: number;
  stepIndex: number;
  steps: TourStep[];
  start: () => void;
  nextModalSlide: () => void;
  startTour: () => void;
  nextStep: () => void;
  skip: () => void;
  restart: () => void;
}

const OnboardingContext = createContext<OnboardingContextValue | null>(null);

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const { data: user } = useCurrentUser();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [phase, setPhase] = useState<"modal" | "tour" | null>(null);
  const [modalSlide, setModalSlide] = useState(0);
  const [stepIndex, setStepIndex] = useState(0);

  const steps = useMemo(
    () => (user?.account_type === "coach" ? COACH_STEPS : SINGLE_STEPS),
    [user?.account_type]
  );

  const completeMutation = useMutation({
    mutationFn: api.auth.completeOnboarding,
    onSuccess: (data) => queryClient.setQueryData(["auth", "me"], data),
  });

  const start = useCallback(() => {
    setPhase("modal");
    setModalSlide(0);
    setStepIndex(0);
  }, []);

  const nextModalSlide = useCallback(() => {
    setModalSlide((s) => s + 1);
  }, []);

  const startTour = useCallback(() => {
    setPhase("tour");
    setStepIndex(0);
  }, []);

  const nextStep = useCallback(() => {
    setStepIndex((i) => {
      const next = i + 1;
      if (next >= steps.length) {
        setPhase(null);
        completeMutation.mutate();
        return i;
      }
      return next;
    });
  }, [steps.length, completeMutation]);

  const skip = useCallback(() => {
    setPhase(null);
    completeMutation.mutate();
  }, [completeMutation]);

  const restart = useCallback(() => {
    start();
  }, [start]);

  const value: OnboardingContextValue = {
    phase,
    modalSlide,
    stepIndex,
    steps,
    start,
    nextModalSlide,
    startTour,
    nextStep,
    skip,
    restart,
  };

  return <OnboardingContext.Provider value={value}>{children}</OnboardingContext.Provider>;
}

export function useOnboarding() {
  const ctx = useContext(OnboardingContext);
  if (!ctx) throw new Error("useOnboarding must be used within OnboardingProvider");
  return ctx;
}
```

Hinweis: `navigate` wird hier importiert, aber noch nicht verwendet (kommt in Task 6 für die routenübergreifende Navigation zum Einsatz, wenn `OnboardingTooltip` die `route`-Funktion eines Steps aufruft - dieser Task legt nur den Grund-State an). Falls `tsc` einen "unused variable"-Fehler wirft, `navigate` vorerst aus dem Context-Wert NICHT exportieren, sondern nur lokal halten (wird in Task 6 tatsächlich gebraucht, wenn `OnboardingTooltip` selbst `useNavigate` aufruft statt über den Context - dann kann die `navigate`-Zeile hier in Task 4 ersatzlos wieder entfernt werden). Am einfachsten: `useNavigate`-Import und die `navigate`-Zeile in diesem Task erstmal weglassen, da sie hier noch nicht gebraucht werden - `OnboardingTooltip` in Task 6 ruft `useNavigate` selbst auf.

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler (Komponente noch nicht eingebunden, aber muss für sich isoliert kompilieren)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/contexts/OnboardingContext.tsx
git commit -m "feat: add OnboardingContext with coach/single tour steps"
```

---

### Task 5: Frontend - `OnboardingModal`

**Files:**
- Create: `frontend/src/components/OnboardingModal.tsx`

- [ ] **Step 1: Komponente schreiben**

```tsx
// frontend/src/components/OnboardingModal.tsx
import { useOnboarding } from "../contexts/OnboardingContext";
import { useCurrentUser } from "../hooks/useCurrentUser";

/** Zwei-Slide-Willkommens-Modal, das vor der Tooltip-Tour gezeigt wird -
 * siehe Design-Spec "Onboarding-Flow" Abschnitt 3. Fade-Transition
 * zwischen den Slides über eine simple key-basierte Remount-Animation
 * (Tailwind `animate-fade-in` via arbitrary keyframes wäre Overkill hier -
 * ein einfacher CSS transition auf opacity reicht). */
export function OnboardingModal() {
  const { modalSlide, nextModalSlide, startTour, skip } = useOnboarding();
  const { data: user } = useCurrentUser();
  const isCoach = user?.account_type === "coach";

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-4">
      <div className="relative w-full max-w-md rounded-xl border border-white/10 bg-surface p-6 shadow-2xl transition-all duration-300">
        <button
          onClick={skip}
          className="absolute right-4 top-4 text-xs text-slate-500 hover:text-white"
        >
          Skip
        </button>

        {modalSlide === 0 && (
          <div className="animate-[fadeIn_0.3s_ease-out] space-y-3">
            <p className="text-2xl">👋</p>
            <h1 className="text-xl font-semibold text-white">Welcome to BodyComp Tracker</h1>
            <p className="text-sm text-slate-400">
              {isCoach
                ? "Let's get you set up to track your clients' progress."
                : "Let's get you set up to track your own progress."}
            </p>
            <button
              onClick={nextModalSlide}
              className="mt-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90"
            >
              Next
            </button>
          </div>
        )}

        {modalSlide === 1 && (
          <div className="animate-[fadeIn_0.3s_ease-out] space-y-3">
            <h2 className="text-lg font-semibold text-white">Here's what we'll show you</h2>
            <ul className="space-y-1.5 text-sm text-slate-300">
              {isCoach ? (
                <>
                  <li>1. Adding your first client</li>
                  <li>2. Sharing the check-in link</li>
                  <li>3. Reviewing check-ins</li>
                </>
              ) : (
                <>
                  <li>1. Uploading your first photos</li>
                  <li>2. Your timeline</li>
                  <li>3. Comparing progress photos</li>
                </>
              )}
            </ul>
            <button
              onClick={startTour}
              className="mt-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90"
            >
              Let's go
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: `fadeIn`-Keyframe zu Tailwind-Config ergänzen**

Prüfe `frontend/tailwind.config.js` (oder `.ts`) - falls dort bereits ein `theme.extend.keyframes`-Block existiert, dort ergänzen, sonst neu anlegen:

```js
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/OnboardingModal.tsx frontend/tailwind.config.js
git commit -m "feat: add OnboardingModal with two welcome slides"
```

(Falls die Tailwind-Config-Datei `.ts` statt `.js` heißt, den tatsächlichen Dateinamen im `git add` verwenden - vorher mit `ls frontend/tailwind.config.*` prüfen.)

---

### Task 6: Frontend - `OnboardingTooltip` (Spotlight + Sprechblase)

**Files:**
- Create: `frontend/src/components/OnboardingTooltip.tsx`

- [ ] **Step 1: Komponente schreiben**

```tsx
// frontend/src/components/OnboardingTooltip.tsx
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useOnboarding } from "../contexts/OnboardingContext";

/** Zeigt einen abgedunkelten Hintergrund mit "Spotlight"-Loch um das
 * Ziel-Element (per box-shadow-Trick, keine Library) + eine Sprechblase
 * daneben - siehe Design-Spec "Onboarding-Flow" Abschnitt 3+5. Steps mit
 * `route` navigieren zuerst dorthin und pollen kurz, bis das Ziel-Element
 * im DOM auftaucht (z.B. nach dem Anlegen eines Klienten). */
export function OnboardingTooltip() {
  const { phase, stepIndex, steps, nextStep, skip } = useOnboarding();
  const navigate = useNavigate();
  const { clientId } = useParams<{ clientId: string }>();
  const [rect, setRect] = useState<DOMRect | null>(null);

  const step = steps[stepIndex];
  const isLastStep = stepIndex === steps.length - 1;

  useEffect(() => {
    if (phase !== "tour" || !step) return;

    if (step.route) {
      const targetClientId = clientId ? Number(clientId) : NaN;
      // Nur navigieren, wenn nötig - vermeidet einen Redirect-Loop, falls
      // der Step bereits auf der richtigen Route ist (z.B. Sidebar-Nav-
      // Punkte, die von derselben Client-Route aus erreichbar sind).
      if (!Number.isNaN(targetClientId)) {
        navigate(step.route(targetClientId));
      }
    }

    let cancelled = false;
    let attempts = 0;
    const poll = () => {
      if (cancelled) return;
      const el = document.querySelector(`[data-tour="${step.dataTour}"]`);
      if (el) {
        setRect(el.getBoundingClientRect());
        return;
      }
      attempts += 1;
      if (attempts < 40) {
        // ~4s Timeout (40 x 100ms) - danach bleibt die Sprechblase
        // ausgeblendet statt endlos zu pollen (z.B. wenn ein Coach-Account
        // Schritt 2 erreicht, ohne vorher wirklich einen Klienten angelegt
        // zu haben, siehe Design-Spec Abschnitt 4 "pausiert").
        setTimeout(poll, 100);
      }
    };
    setRect(null);
    poll();

    return () => {
      cancelled = true;
    };
  }, [phase, step, navigate, clientId]);

  if (phase !== "tour" || !step) return null;

  return (
    <div className="fixed inset-0 z-[100]">
      {rect && (
        <>
          {/* Spotlight: ein transparentes Rechteck exakt über dem Ziel-
              Element, mit einem riesigen box-shadow, der den Rest des
              Viewports abdunkelt - kein SVG-Masking o.ä. nötig. */}
          <div
            className="pointer-events-none fixed rounded-lg transition-all duration-300"
            style={{
              top: rect.top - 6,
              left: rect.left - 6,
              width: rect.width + 12,
              height: rect.height + 12,
              boxShadow: "0 0 0 9999px rgba(0,0,0,0.7)",
            }}
          />
          <div
            className="fixed z-[101] w-72 rounded-xl border border-accent/30 bg-surface p-4 shadow-2xl transition-all duration-300"
            style={{
              top: rect.bottom + 12,
              left: Math.min(rect.left, window.innerWidth - 300),
            }}
          >
            <p className="mb-1 text-sm font-semibold text-white">{step.title}</p>
            <p className="mb-3 text-xs text-slate-400">{step.body}</p>
            <div className="flex items-center justify-between">
              <button onClick={skip} className="text-xs text-slate-500 hover:text-white">
                Skip tour
              </button>
              <button
                onClick={nextStep}
                className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-slate-900 hover:opacity-90"
              >
                {isLastStep ? "Done" : "Next"}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/OnboardingTooltip.tsx
git commit -m "feat: add OnboardingTooltip with spotlight effect"
```

---

### Task 7: `data-tour`-Attribute an Ziel-Elementen ergänzen

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`
- Modify: `frontend/src/pages/Unprocessed.tsx`
- Modify: `frontend/src/pages/Settings.tsx`
- Modify: `frontend/src/components/ClientShell.tsx`

- [ ] **Step 1: Dashboard.tsx - "Neuen Kunden anlegen"-Button**

Den Button in der `PageHeader`-`actions`-Prop (`onClick={() => setShowForm((s) => !s)}`) um `data-tour="dashboard-new-client"` ergänzen.

- [ ] **Step 2: Unprocessed.tsx - "Fotos hochladen"-Button**

Den Button (`onClick={() => fileInputRef.current?.click()}`) um `data-tour="unprocessed-upload"` ergänzen.

- [ ] **Step 3: Settings.tsx - Check-in-Link-Bereich**

Das äußere `<div>` des Check-in-Link-Blocks (`<p className="text-sm font-medium text-white">Check-in-Link für den Klienten</p>` und alles darunter bis zum "Link neu generieren"-Button) bekommt `data-tour="settings-checkin-link"` auf seinem umschließenden `<div>`.

- [ ] **Step 4: ClientShell.tsx - Nav-Punkte**

In der `NAV_ITEMS.map(...)`-Schleife (kommt zweimal vor: Mobile-Overlay und Desktop-Sidebar) jedem `NavLink` ein `data-tour={`nav-${item.to}`}` ergänzen (nutzt den bestehenden `item.to`-Wert, ergibt z.B. `nav-timeline`, `nav-checkins`, `nav-compare` - passt exakt zu den in Task 4 definierten `dataTour`-Werten).

- [ ] **Step 5: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx frontend/src/pages/Unprocessed.tsx frontend/src/pages/Settings.tsx frontend/src/components/ClientShell.tsx
git commit -m "feat: add data-tour attributes to onboarding target elements"
```

---

### Task 8: Einbindung in `App.tsx` + Auto-Start + Replay-Button

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/Account.tsx`

- [ ] **Step 1: `OnboardingProvider` um die Routen legen**

In `frontend/src/App.tsx`, `OnboardingProvider` importieren und um den kompletten `<Routes>`-Baum legen:

```tsx
import { OnboardingProvider } from "./contexts/OnboardingContext";
import { OnboardingModal } from "./components/OnboardingModal";
import { OnboardingTooltip } from "./components/OnboardingTooltip";
```

```tsx
export default function App() {
  return (
    <OnboardingProvider>
      <Routes>
        {/* ... bestehende Routen unverändert ... */}
      </Routes>
      <OnboardingModalGate />
    </OnboardingProvider>
  );
}
```

Da `OnboardingModal`/`OnboardingTooltip` selbst über `useOnboarding()` ihren `phase`-State lesen und bei `null` `null` rendern (siehe Task 5/6 - `OnboardingModal` muss dafür noch angepasst werden, aktuell rendert es IMMER etwas, wenn eingebunden), braucht es einen kleinen Gate-Wrapper. Füge in `App.tsx` (oder in einer eigenen kleinen Datei `frontend/src/components/OnboardingGate.tsx`, falls `App.tsx` dadurch zu unübersichtlich würde - am pragmatischsten aber direkt inline in `App.tsx`) diese Komponente hinzu:

```tsx
function OnboardingModalGate() {
  const { phase } = useOnboarding();
  if (phase === "modal") return <OnboardingModal />;
  if (phase === "tour") return <OnboardingTooltip />;
  return null;
}
```

(`useOnboarding` entsprechend zusätzlich in `App.tsx` importieren.)

- [ ] **Step 2: Auto-Start beim ersten Login**

Der Auto-Start-Trigger lebt am saubersten in `AppShell.tsx` (dort ist `useCurrentUser` bereits geladen und es ist der gemeinsame Rahmen für alle eingeloggten Seiten). In `frontend/src/components/AppShell.tsx`:

```tsx
import { useEffect } from "react";
import { useOnboarding } from "../contexts/OnboardingContext";
```

Im Komponentenkörper, nach der bestehenden `const { data: user } = useCurrentUser();`-Zeile:

```tsx
  const { start } = useOnboarding();
  useEffect(() => {
    if (user && user.onboarding_completed_at === null) {
      start();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);
```

(Absichtlich nur auf `user?.id` reagieren, nicht auf das ganze `user`-Objekt - sonst würde der Effect bei JEDEM Refetch von `useCurrentUser` erneut prüfen und die Tour ggf. mehrfach anstoßen, wenn `onboarding_completed_at` durch einen zwischenzeitlichen Refetch kurz noch `null` erscheint, bevor die Mutation durchgeschlagen hat.)

- [ ] **Step 3: Replay-Button in Account.tsx**

In `frontend/src/pages/Account.tsx`: `useOnboarding` importieren, im `Account()`-Komponentenkörper `const { restart } = useOnboarding();` ergänzen, und im JSX (z.B. direkt nach der `<BillingSection />`-Zeile, in einer eigenen kleinen `Card`) einen Button hinzufügen:

```tsx
      <Card title="Need a refresher?">
        <button
          onClick={restart}
          className="rounded-lg border border-white/10 px-4 py-2 text-sm font-medium text-white hover:bg-white/5"
        >
          Restart tour
        </button>
      </Card>
```

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler

- [ ] **Step 5: Manuelle Durchsicht**

Dev-Server starten, mit einem frischen Test-Account (oder einem Account mit `onboarding_completed_at = NULL` in der DB) einloggen: Modal erscheint automatisch, beide Slides + Übergänge funktionieren, Tour startet, Spotlight+Sprechblase folgen den richtigen Elementen, "Skip"/"Done" schließen die Tour und rufen den Completion-Endpunkt auf (per Netzwerk-Tab prüfbar). Danach: Account-Seite → "Restart tour" löst die Tour erneut aus, ohne dass ein erneuter Login nötig ist.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/AppShell.tsx frontend/src/pages/Account.tsx
git commit -m "feat: wire onboarding flow into app shell with auto-start and replay"
```

---

### Task 9: Finaler Review + Branch abschließen

- [ ] **Step 1: Vollständigen Typecheck laufen lassen**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler

- [ ] **Step 2: Backend-Testsuite laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: alle Tests grün (bis auf den bekannten, unabhängigen `test_gemini_key_is_scoped_per_account`-Fall bei lokal gesetztem `.env`-Key)

- [ ] **Step 3: Manuelle Gesamt-Durchsicht**

Kompletten Flow für BEIDE Account-Typen einmal komplett durchklicken (Coach: Klient anlegen → Settings → Check-ins; Single: Upload → Timeline → Compare), inklusive des Falls "Coach-Account ohne Klienten pausiert an Schritt 1, bis wirklich ein Klient angelegt wurde" (siehe Design-Spec Abschnitt 4).

- [ ] **Step 4: `superpowers:finishing-a-development-branch` nutzen**

Tests verifizieren (bereits in Step 1/2 geschehen), Merge nach `dev` anbieten, danach `dev`→`main` nur nach expliziter Nutzer-Bestätigung.
