# Öffentliche Landingpage (Stufe 5f) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Öffentliche Marketing-Landingpage unter `/`, Coach-Zielgruppe führt inhaltlich, Single-Nutzer als gleichwertig sichtbare zweite Spur. Eingeloggte Nutzer werden sofort automatisch weitergeleitet.

**Architecture:** Neue `Landing.tsx`-Seite außerhalb `RequireAuth`. Die bisherige geschützte Root-Weiterleitung (`ClientRedirect`) zieht von `/` auf `/app` um. Zwei bestehende Stellen (`Login.tsx`, `AppShell.tsx`) werden auf den neuen Pfad angepasst.

**Tech Stack:** React, TypeScript, Tailwind CSS, react-router-dom.

---

### Task 1: Routing-Umbau - `/app` als neuer geschützter Root, `/` frei für die Landingpage

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/Login.tsx`
- Modify: `frontend/src/components/AppShell.tsx`

- [ ] **Step 1: `App.tsx` - Index-Route von `/` auf `/app` verschieben**

In `frontend/src/App.tsx`, den bestehenden Block:

```tsx
        <Route element={<AppShell />}>
          <Route index element={<ClientRedirect />} />
          <Route path="dashboard" element={<Dashboard />} />
```

ändern zu:

```tsx
        <Route element={<AppShell />}>
          <Route path="app" element={<ClientRedirect />} />
          <Route path="dashboard" element={<Dashboard />} />
```

(`index` wird zu einem benannten `path="app"` - dadurch ist `/app` erreichbar statt der bisherigen `/`. Kein `Landing`-Import/-Route wird hier ergänzt, das passiert erst in Task 3, wenn die Komponente existiert - dieser Task beschränkt sich bewusst auf den Umbau des bestehenden geschützten Teils, damit `/` danach frei ist.)

- [ ] **Step 2: `Login.tsx` - Redirect nach Login auf `/app`**

In `frontend/src/pages/Login.tsx`, `loginMutation`s `onSuccess`:

```tsx
    onSuccess: (user) => {
      queryClient.setQueryData(["auth", "me"], user);
      navigate("/app");
    },
```

Den alten Kommentar über der Zeile (der auf `"/"` verweist) entsprechend anpassen:

```tsx
      // "/app" wird über ClientRedirect ausgewertet, das bereits beide
      // Kontotypen korrekt behandelt (coach -> Dashboard, single -> das
      // eine Client-Profil) - kein eigener Pfad pro Kontotyp nötig.
```

- [ ] **Step 3: `AppShell.tsx` - Logo-Link für Single-Accounts auf `/app`**

In `frontend/src/components/AppShell.tsx`:

```tsx
            <Link
              to={user?.account_type === "coach" ? "/dashboard" : "/app"}
```

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: Fehler dahingehend, dass `/` aktuell auf keine Route mehr matcht, wenn man es im Browser aufruft (kein TS-Fehler, nur zur Kenntnis - das wird in Task 3 behoben, wenn `Landing.tsx` als neue Root-Route ergänzt wird). Reiner TS-Compile darf keine Fehler zeigen.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/pages/Login.tsx frontend/src/components/AppShell.tsx
git commit -m "refactor: move protected root redirect from / to /app"
```

---

### Task 2: `Landing.tsx` - Hero + Feature-Grid + How-it-works

**Files:**
- Create: `frontend/src/pages/Landing.tsx`

- [ ] **Step 1: Grundgerüst + Auth-Redirect + Hero**

```tsx
// frontend/src/pages/Landing.tsx
import { Link, Navigate } from "react-router-dom";
import { useCurrentUser } from "../hooks/useCurrentUser";

const FEATURES = [
  {
    icon: "🔗",
    title: "Magic-link check-ins",
    body: "Clients submit weight and progress photos through a link - no account, no app download for them.",
  },
  {
    icon: "🤖",
    title: "AI-powered comparisons",
    body: "Get an objective before/after read on any two check-ins - muscle definition, symmetry, conditioning.",
  },
  {
    icon: "📈",
    title: "Timeline & stats",
    body: "Every check-in lands on a clean visual timeline with weight trends and progress photos side by side.",
  },
  {
    icon: "🔔",
    title: "Automatic reminders",
    body: "Set a check-in cadence once - BodyComp nudges whoever's falling behind, so you don't have to chase.",
  },
];

/** Öffentliche Marketing-Seite unter "/" - siehe Design-Spec
 * "Landingpage" Abschnitt "Routing-Umbau". Eingeloggte Nutzer werden
 * sofort zu /app weitergeleitet, sehen diese Seite nie. */
export default function Landing() {
  const { data: user, isLoading } = useCurrentUser();

  if (isLoading) return null;
  if (user) return <Navigate to="/app" replace />;

  return (
    <div className="min-h-screen bg-background text-slate-100">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-5 sm:px-6">
        <span className="text-sm font-semibold tracking-wide text-white">
          BodyComp <span className="text-accent">Tracker</span>
        </span>
        <Link
          to="/login"
          className="text-sm font-medium text-slate-300 hover:text-white"
        >
          Log in
        </Link>
      </header>

      <section className="mx-auto max-w-4xl px-4 pb-20 pt-12 text-center sm:px-6 sm:pt-20">
        <h1 className="text-4xl font-bold leading-tight text-white sm:text-5xl">
          Run your coaching business,{" "}
          <span className="text-accent">not spreadsheets</span>
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-lg text-slate-400">
          Track every client's progress photos, weight, and check-ins in one place -
          or use it solo to track your own transformation.
        </p>
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
      </section>

      <section className="mx-auto max-w-6xl px-4 pb-20 sm:px-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map((f) => (
            <div
              key={f.title}
              className="rounded-xl border border-white/5 bg-surface p-5"
            >
              <span className="text-2xl">{f.icon}</span>
              <p className="mt-3 text-sm font-semibold text-white">{f.title}</p>
              <p className="mt-1.5 text-sm text-slate-400">{f.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-5xl px-4 pb-20 sm:px-6">
        <h2 className="text-center text-2xl font-bold text-white">How it works</h2>
        <div className="mt-8 grid grid-cols-1 gap-6 sm:grid-cols-3">
          <HowItWorksStep
            number={1}
            title="Add a client"
            body="Create a client profile in seconds - or just start tracking yourself."
          />
          <HowItWorksStep
            number={2}
            title="Share the check-in link"
            body="Your client bookmarks their personal link and submits photos + weight whenever it's time."
          />
          <HowItWorksStep
            number={3}
            title="Review progress"
            body="See everything on a timeline, compare any two dates, leave feedback."
          />
        </div>
        <p className="mx-auto mt-6 max-w-md text-center text-xs text-slate-600">
          Solo tracking works the same way, minus the sharing step - it's just you and your own timeline.
        </p>
      </section>
    </div>
  );
}

function HowItWorksStep({ number, title, body }: { number: number; title: string; body: string }) {
  return (
    <div className="text-center">
      <div className="mx-auto flex h-9 w-9 items-center justify-center rounded-full bg-accent/15 text-sm font-semibold text-accent">
        {number}
      </div>
      <p className="mt-3 text-sm font-semibold text-white">{title}</p>
      <p className="mt-1.5 text-sm text-slate-400">{body}</p>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler (Komponente noch nicht in `App.tsx` eingebunden, das passiert in Task 4 - reiner Isoliert-Check hier)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Landing.tsx
git commit -m "feat: add landing page hero, features, and how-it-works sections"
```

---

### Task 3: `Landing.tsx` - Preise + Schluss-CTA + Footer

**Files:**
- Modify: `frontend/src/pages/Landing.tsx`

- [ ] **Step 1: Preis-Konstante + Preis-Sektion ergänzen**

Nach der bestehenden `FEATURES`-Konstante ergänzen (Preise 1:1 aus `Account.tsx`s `COACH_PLANS` übernommen, siehe Design-Spec "Preise" - bei einer künftigen Preisänderung dort UND hier anpassen, keine gemeinsame Quelle in diesem Scope):

```tsx
const PRICING_PLANS: {
  key: string;
  label: string;
  price: string;
  featured?: boolean;
  features: string[];
}[] = [
  {
    key: "single",
    label: "Solo",
    price: "€4.99/month",
    features: ["Unlimited check-ins", "Your own timeline & compare", "No trial needed to try it - 2 free check-ins"],
  },
  {
    key: "starter",
    label: "Starter",
    price: "€19/month",
    features: ["Up to 5 clients", "Unlimited photos & check-ins", "Magic-link submission"],
  },
  {
    key: "pro",
    label: "Pro",
    price: "€49/month",
    featured: true,
    features: ["Up to 20 clients", "Everything in Starter", "Priority support"],
  },
  {
    key: "business",
    label: "Business",
    price: "€99/month",
    features: ["Unlimited clients", "Everything in Pro", "For large coaching teams"],
  },
];
```

Vor dem schließenden `</div>` der Wurzelkomponente (nach der "How it works"-Section, vor Ende der Funktion) ergänzen:

```tsx
      <section className="mx-auto max-w-6xl px-4 pb-20 sm:px-6">
        <h2 className="text-center text-2xl font-bold text-white">Pricing</h2>
        <p className="mx-auto mt-2 max-w-md text-center text-sm text-slate-400">
          14-day free trial on coach plans, no card tricks. Solo plan starts free - subscribe
          whenever you outgrow the free allowance.
        </p>
        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {PRICING_PLANS.map((plan) => (
            <div
              key={plan.key}
              className={`relative rounded-xl border p-5 ${
                plan.featured ? "border-accent bg-accent/5" : "border-white/5 bg-surface"
              }`}
            >
              {plan.featured && (
                <span className="absolute -top-2.5 left-4 rounded-full bg-accent px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-900">
                  Popular
                </span>
              )}
              <p className="text-sm font-semibold text-white">{plan.label}</p>
              <p className="mt-1 text-xl font-bold text-white">{plan.price}</p>
              <ul className="mt-3 space-y-1 text-xs text-slate-400">
                {plan.features.map((f) => (
                  <li key={f} className="flex items-start gap-1.5">
                    <span className="text-accent">✓</span> {f}
                  </li>
                ))}
              </ul>
              <Link
                to="/signup"
                className="mt-4 block w-full rounded-lg bg-accent px-3 py-2 text-center text-sm font-medium text-slate-900 hover:opacity-90"
              >
                Get started
              </Link>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-3xl px-4 pb-20 text-center sm:px-6">
        <p className="text-sm text-slate-500">
          Built for coaches who want less admin and more coaching - and for anyone who just
          wants an honest record of their own progress.
        </p>
        <Link
          to="/signup"
          className="mt-6 inline-block rounded-lg bg-accent px-6 py-3 text-sm font-semibold text-slate-900 transition-opacity hover:opacity-90"
        >
          Get started for free
        </Link>
      </section>

      <footer className="border-t border-white/5 px-4 py-8 sm:px-6">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 text-xs text-slate-500">
          <span>© {new Date().getFullYear()} BodyComp Tracker</span>
          <div className="flex gap-4">
            <Link to="/login" className="hover:text-white">Log in</Link>
            <Link to="/impressum" className="hover:text-white">Legal notice</Link>
            <Link to="/datenschutz" className="hover:text-white">Privacy</Link>
            <Link to="/agb" className="hover:text-white">Terms</Link>
          </div>
        </div>
      </footer>
```

(Einfügeposition: direkt nach der bestehenden "How it works"-`<section>` aus Task 2, vor dem schließenden `</div>` der Wurzelkomponente.)

Hinweis zu `new Date()`: das ist normaler React-Komponenten-Code zur Render-Zeit im Browser, kein Workflow-Script - hier uneingeschränkt erlaubt (die `Date.now()`/`new Date()`-Einschränkung gilt nur für Workflow-Skripte, nicht für normalen Anwendungscode).

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Landing.tsx
git commit -m "feat: add pricing, closing CTA, and footer to landing page"
```

---

### Task 4: Einbindung als öffentliche Route unter `/`

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Route ergänzen**

In `frontend/src/App.tsx`: `Landing`-Import ergänzen (`import Landing from "./pages/Landing";`), und als erste Route in `<Routes>` ergänzen:

```tsx
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler

- [ ] **Step 3: Manuell prüfen**

Dev-Server starten. Als Gast `/` öffnen → Landingpage sichtbar, alle CTA-Links führen zu `/signup` bzw. `/login`, Footer-Links funktionieren. Einloggen → danach `/app` besucht/automatisch dahin geleitet, Landingpage nicht mehr sichtbar. `/` erneut manuell aufrufen während eingeloggt → sofortige Weiterleitung zu `/app`, kein Flackern der Marketing-Seite. Schmale Viewport-Breite (375px) prüfen - Hero/Feature-Grid/Preise bleiben lesbar, kein horizontales Scrollen.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: mount landing page at public root route"
```

---

### Task 5: Finaler Review + Branch abschließen

- [ ] **Step 1: Vollständigen Typecheck laufen lassen**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler

- [ ] **Step 2: Backend-Testsuite laufen lassen** (reine Frontend-Änderung, Standard-Check vor Merge)

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: alle Tests grün (bis auf den bekannten, unabhängigen `test_gemini_key_is_scoped_per_account`-Fall)

- [ ] **Step 3: Manuelle Gesamt-Durchsicht**

Kompletten Flow einmal durchklicken: Landingpage (Gast) → Signup → Verify → Login → landet in `/app` → Dashboard/Timeline. Sicherstellen, dass keine bestehende interne Verlinkung mehr auf die alte `/`-Bedeutung ("geschützter Root") zeigt (`grep -rn 'to="/"' frontend/src/` sollte jetzt nur noch Treffer in `Landing.tsx` selbst und ggf. im Footer/Header dieser Seite zeigen, keine Treffer mehr in geschützten Seiten).

- [ ] **Step 4: `superpowers:finishing-a-development-branch` nutzen**

Tests verifizieren (bereits in Step 1/2 geschehen), Merge nach `dev` anbieten (inkl. Push nach origin), danach `dev`→`main` nur nach expliziter Nutzer-Bestätigung.
