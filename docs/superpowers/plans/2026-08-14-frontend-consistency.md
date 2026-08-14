# Frontend-Konsistenz & Navigations-Überarbeitung Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Konsistente Layout-Schicht (verschachtelte `AppShell`/`ClientShell`-Komponenten statt einer Bedingungs-Komponente), vertikale einklappbare Kunden-Navi, einheitlicher Seiten-Header, und ein modernisiertes Dashboard mit Suche/Filter.

**Architecture:** React-Router-Nesting ersetzt die bisherige einzelne `Layout.tsx`. `AppShell` (immer gleich) → `ClientShell` (nur in Kunden-Routen) → Seiten-Inhalt. Eine gemeinsame `PageHeader`-Komponente vereinheitlicht Überschriften/Abstände auf allen Seiten.

**Tech Stack:** React, TypeScript, React Router v6 (nested routes/Outlet), Tailwind CSS, `@tanstack/react-query`, FastAPI/SQLAlchemy (kleine Backend-Erweiterung für Dashboard-Kennzahlen).

---

## Part 1 — Backend: Foto-Kennzahlen pro Kunde

### Task 1: `photo_count` + `last_activity` in `ClientOut`

**Files:**
- Modify: `backend/app/schemas/client.py`
- Modify: `backend/app/routers/clients.py`
- Test: `backend/tests/test_clients_router.py`

- [ ] **Step 1: Failing test**

Append to `backend/tests/test_clients_router.py`:

```python
def test_list_clients_includes_photo_count_and_last_activity(client, db_session):
    from datetime import date, datetime

    from app.models.photo import Photo, ProcessingStatus

    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()

    db_session.add(Photo(
        client_id=created["id"],
        filename="a.jpg",
        original_path="photos_processed/1/2026-01-01/a.jpg",
        taken_at=datetime(2026, 1, 1, 12, 0, 0),
        status=ProcessingStatus.PROCESSED,
    ))
    db_session.add(Photo(
        client_id=created["id"],
        filename="b.jpg",
        original_path="photos_processed/1/2026-02-01/b.jpg",
        taken_at=datetime(2026, 2, 1, 12, 0, 0),
        status=ProcessingStatus.PROCESSED,
    ))
    db_session.commit()

    list_resp = client.get("/api/clients")
    body = list_resp.json()
    assert body[0]["photo_count"] == 2
    assert body[0]["last_activity"] == "2026-02-01"


def test_list_clients_last_activity_is_null_without_photos(client, db_session):
    _login(client, db_session)
    client.post("/api/clients", json={"name": "Max"})

    body = client.get("/api/clients").json()
    assert body[0]["photo_count"] == 0
    assert body[0]["last_activity"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_clients_router.py -v`
Expected: FAIL — `KeyError: 'photo_count'` (Feld existiert noch nicht in der Response)

- [ ] **Step 3: `ClientOut` erweitern**

In `backend/app/schemas/client.py`, füge zur `ClientOut`-Klasse hinzu (nach `created_at`):

```python
    photo_count: int
    last_activity: date_ | None
```

- [ ] **Step 4: `list_clients` um die Aggregation erweitern**

Read `backend/app/routers/clients.py` in full first (bestätige die aktuelle Struktur passt zu dem unten gezeigten Diff). Ersetze `list_clients`:

```python
@router.get("", response_model=list[ClientOut])
def list_clients(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    from sqlalchemy import func

    from app.models.photo import Photo

    clients = (
        db.query(Client)
        .filter(Client.owner_id == current_user.id)
        .order_by(Client.created_at)
        .all()
    )

    stats = dict(
        db.query(Photo.client_id, func.count(Photo.id))
        .filter(Photo.client_id.in_([c.id for c in clients]))
        .group_by(Photo.client_id)
        .all()
    )
    last_activity = dict(
        db.query(Photo.client_id, func.max(Photo.taken_at))
        .filter(Photo.client_id.in_([c.id for c in clients]))
        .group_by(Photo.client_id)
        .all()
    )

    result = []
    for c in clients:
        out = ClientOut.model_validate(c)
        out.photo_count = stats.get(c.id, 0)
        activity = last_activity.get(c.id)
        out.last_activity = activity.date() if activity else None
        result.append(out)
    return result
```

Add `from app.schemas.client import ClientCreate, ClientOut, ClientUpdate` bleibt unverändert (bereits vorhanden) — nur die Funktion selbst wird ersetzt. Zwei separate Aggregations-Queries statt einer JOIN-Query, um die Größe der Änderung klein zu halten und keine bestehenden Query-Strukturen anzufassen — bei der aktuell kleinen erwarteten Kundenzahl pro Coach kein Performance-Thema.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_clients_router.py -v`
Expected: `6 passed` (4 bestehende + 2 neue)

- [ ] **Step 6: Run full suite**

Run: `cd backend && .venv/Scripts/python -m pytest -v`
Expected: alle grün (die anderen Endpunkte, die `ClientOut` auch nutzen — `create_client`, `get_client`, `update_client` — geben `photo_count`/`last_activity` jetzt implizit über `ClientOut`s Feld-Defaults zurück; da diese über `response_model=ClientOut` und `from_attributes=True` direkt vom SQLAlchemy-Objekt validiert werden, das selbst KEINE `photo_count`/`last_activity`-Attribute hat, würde das crashen — prüfe das explizit im nächsten Schritt).

- [ ] **Step 7: `create_client`/`get_client`/`update_client` korrigieren, falls nötig**

Da `photo_count`/`last_activity` neue **Pflichtfelder** in `ClientOut` sind, aber KEINE Spalten auf dem `Client`-SQLAlchemy-Model, schlägt `ClientOut.model_validate(client_row)` in `create_client`/`get_client`/`update_client` fehl (Pydantic kann die Felder nicht aus dem ORM-Objekt lesen). Führe die volle Testsuite aus (Schritt 6) und lies den tatsächlichen Fehler — falls das auftritt (erwartet), behebe es, indem du in `app/routers/clients.py` für `create_client`, `get_client`, `update_client` jeweils die Rückgabe explizit über einen kleinen Helfer baust statt das rohe SQLAlchemy-Objekt zurückzugeben:

```python
def _to_client_out(client_row: Client, db: Session) -> ClientOut:
    from sqlalchemy import func

    from app.models.photo import Photo

    photo_count = (
        db.query(func.count(Photo.id)).filter(Photo.client_id == client_row.id).scalar() or 0
    )
    last_activity_dt = (
        db.query(func.max(Photo.taken_at)).filter(Photo.client_id == client_row.id).scalar()
    )
    out = ClientOut.model_validate(client_row)
    out.photo_count = photo_count
    out.last_activity = last_activity_dt.date() if last_activity_dt else None
    return out
```

Ersetze in `create_client`, `get_client`, `update_client` jeweils `return client_row` (bzw. `return db.refresh(client_row)`-artige Muster) durch `return _to_client_out(client_row, db)`. Lies die drei Funktionen im aktuellen File genau, um die exakte Ersetzungsstelle zu finden — die Grundstruktur (Depends, Response-Model) bleibt gleich, nur die letzte `return`-Zeile ändert sich.

Run: `cd backend && .venv/Scripts/python -m pytest -v`
Expected: alle grün.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/client.py backend/app/routers/clients.py backend/tests/test_clients_router.py
git commit -m "feat: add photo_count and last_activity to ClientOut for dashboard cards"
```

---

## Part 2 — Frontend: Layout-Infrastruktur

### Task 2: `PageHeader`-Komponente + Abstands-Konstanten

**Files:**
- Create: `frontend/src/components/PageHeader.tsx`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: `Client`-Typ um die neuen Felder erweitern**

In `frontend/src/types/index.ts`, im `Client`-Interface, füge nach `created_at` hinzu:

```typescript
  photo_count: number;
  last_activity: string | null; // ISO YYYY-MM-DD
```

- [ ] **Step 2: `PageHeader.tsx` schreiben**

```tsx
// frontend/src/components/PageHeader.tsx
import type { ReactNode } from "react";

/** Einheitliche Seiten-Überschrift für alle eingeloggten Seiten
 * (Dashboard, Account, alle Kunden-Unterseiten) - siehe Design-Spec
 * Abschnitt "Gemeinsamer Seiten-Header & Abstände". Ersetzt die bisher
 * pro Seite leicht unterschiedlich gebauten <h1>-Blöcke. */
export default function PageHeader({
  title,
  actions,
}: {
  title: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex items-center justify-between">
      <h1 className="text-xl font-semibold text-white">{title}</h1>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: Fehler in `Dashboard.tsx` (verwendet `c.age`/fehlende Felder nicht, aber der `Client`-Typ hat jetzt Pflichtfelder `photo_count`/`last_activity`, die `api.clients.create`/`update`-Aufrufe nicht liefern müssen, da das response-seitige Felder sind, keine Request-Felder — prüfe, ob `tsc` hier wirklich einen Fehler zeigt; falls ja, behebe ihn erst in Task 3, wenn `Dashboard.tsx` ohnehin überarbeitet wird. Falls `tsc` hier sauber ist, einfach weiter.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/PageHeader.tsx frontend/src/types/index.ts
git commit -m "feat: add shared PageHeader component, extend Client type with photo_count/last_activity"
```

---

### Task 3: `AppShell`-Komponente

**Files:**
- Create: `frontend/src/components/AppShell.tsx`
- Delete: `frontend/src/components/Layout.tsx` (Inhalt wandert in `AppShell` + `ClientShell`, siehe Task 4)

- [ ] **Step 1: `AppShell.tsx` schreiben**

Read `frontend/src/components/Layout.tsx` in full first, um sicherzustellen, dass `useCurrentUser`, `api.auth.logout` exakt so importiert/aufgerufen werden wie bisher.

```tsx
// frontend/src/components/AppShell.tsx
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useCurrentUser } from "../hooks/useCurrentUser";

/** Äußerer Rahmen, identisch auf JEDER eingeloggten Seite - siehe
 * Design-Spec Abschnitt "AppShell (oberer Header)". Enthält keine
 * kunden-spezifische Navigation mehr - das übernimmt ClientShell für
 * /clients/:id/*-Routen (siehe components/ClientShell.tsx). */
export default function AppShell() {
  const { data: user } = useCurrentUser();
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();

  const logoutMutation = useMutation({
    mutationFn: api.auth.logout,
    onSuccess: () => {
      queryClient.clear();
      navigate("/login");
    },
  });

  const onDashboard = location.pathname === "/dashboard";

  return (
    <div className="min-h-screen bg-background text-slate-100">
      <header className="sticky top-0 z-30 border-b border-white/5 bg-background/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold tracking-wide text-white">
              BodyComp <span className="text-accent">Tracker</span>
            </span>
            {user?.account_type === "coach" && (
              <NavLink
                to="/dashboard"
                aria-disabled={onDashboard}
                onClick={(e) => onDashboard && e.preventDefault()}
                className={`text-xs ${
                  onDashboard
                    ? "cursor-default font-medium text-accent"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                Dashboard
              </NavLink>
            )}
          </div>
          <div className="flex items-center gap-3">
            <NavLink
              to="/account"
              className={({ isActive }) =>
                `text-xs ${isActive ? "font-medium text-accent" : "text-slate-400 hover:text-white"}`
              }
            >
              Account
            </NavLink>
            <button
              onClick={() => logoutMutation.mutate()}
              className="text-xs text-slate-400 hover:text-white"
            >
              Logout
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
        <Outlet />
      </main>
    </div>
  );
}
```

- [ ] **Step 2: `Layout.tsx` löschen**

```bash
rm frontend/src/components/Layout.tsx
```

(Wird erst in Task 5 aus `App.tsx` entfernt referenziert — bis dahin zeigt `tsc` einen Importfehler in `App.tsx`, das ist für diesen Zwischenschritt erwartet. Committe trotzdem jetzt schon, Task 5 folgt direkt danach in derselben Session.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/AppShell.tsx
git add -u frontend/src/components/Layout.tsx
git commit -m "feat: add AppShell (replaces Layout.tsx), consistent header across all pages"
```

---

### Task 4: `ClientShell`-Komponente (vertikale Navi + Mini-Header)

**Files:**
- Create: `frontend/src/components/ClientShell.tsx`

- [ ] **Step 1: `ClientShell.tsx` schreiben**

```tsx
// frontend/src/components/ClientShell.tsx
import { useEffect, useState } from "react";
import { NavLink, Outlet, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

const SIDEBAR_COLLAPSED_KEY = "bodycomp:sidebarCollapsed";

const NAV_ITEMS = [
  { to: "timeline", label: "Timeline", icon: "📅" },
  { to: "unprocessed", label: "Import", icon: "📥" },
  { to: "compare", label: "Compare", icon: "🔍" },
  { to: "statistics", label: "Statistik", icon: "📊" },
  { to: "settings", label: "Settings", icon: "⚙️" },
];

/** Nur aktiv innerhalb /clients/:clientId/* - fügt die vertikale
 * Kunden-Navi + Mini-Header (aktueller Kundenname) hinzu, siehe
 * Design-Spec Abschnitt "ClientShell (vertikale Kunden-Navi)". */
export default function ClientShell() {
  const { clientId } = useParams<{ clientId: string }>();
  const [desktopCollapsed, setDesktopCollapsed] = useState(() => {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true";
  });
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(desktopCollapsed));
  }, [desktopCollapsed]);

  const clientQuery = useQuery({
    queryKey: ["clients", clientId],
    queryFn: () => api.clients.get(Number(clientId)),
    enabled: !!clientId,
  });

  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
      isActive ? "bg-accent text-slate-900" : "text-slate-400 hover:bg-white/5 hover:text-white"
    }`;

  return (
    <div className="flex gap-6">
      {/* Mobile: schmale Leiste mit Toggle, Overlay beim Ausklappen */}
      <button
        onClick={() => setMobileOpen(true)}
        className="fixed left-0 top-16 z-20 rounded-r-lg border border-l-0 border-white/10 bg-surface px-2 py-3 text-slate-400 sm:hidden"
        aria-label="Navigation öffnen"
      >
        ☰
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
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "timeline"}
                onClick={() => setMobileOpen(false)}
                className={navLinkClass}
              >
                <span>{item.icon}</span>
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      )}

      {/* Desktop: feste Sidebar, einklappbar */}
      <nav
        className={`hidden shrink-0 flex-col gap-1 sm:flex ${
          desktopCollapsed ? "w-12" : "w-48"
        } transition-all`}
      >
        <button
          onClick={() => setDesktopCollapsed((c) => !c)}
          className="mb-2 self-end rounded-lg p-2 text-slate-500 hover:bg-white/5 hover:text-white"
          aria-label={desktopCollapsed ? "Navigation ausklappen" : "Navigation einklappen"}
        >
          {desktopCollapsed ? "»" : "«"}
        </button>
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "timeline"}
            className={navLinkClass}
            title={desktopCollapsed ? item.label : undefined}
          >
            <span>{item.icon}</span>
            {!desktopCollapsed && item.label}
          </NavLink>
        ))}
      </nav>

      <div className="min-w-0 flex-1">
        {clientQuery.data && (
          <div className="mb-4 flex items-center gap-2 rounded-lg bg-surface/60 px-3 py-1.5 text-sm text-slate-300">
            <span className="text-slate-500">Kunde:</span> {clientQuery.data.name}
          </div>
        )}
        <Outlet />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: Fehler nur noch in `App.tsx` (referenziert `Layout` noch, wird in Task 5 behoben) — keine Fehler in `ClientShell.tsx`/`AppShell.tsx`/`PageHeader.tsx` selbst.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ClientShell.tsx
git commit -m "feat: add ClientShell with collapsible vertical nav and client mini-header"
```

---

### Task 5: `App.tsx` auf verschachtelte Routen umstellen

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: `App.tsx` ersetzen**

```tsx
import { Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import ClientShell from "./components/ClientShell";
import RequireAuth from "./components/RequireAuth";
import ClientRedirect from "./components/ClientRedirect";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import SignupSuccess from "./pages/SignupSuccess";
import VerifyEmail from "./pages/VerifyEmail";
import ForgotPassword from "./pages/ForgotPassword";
import ResetPassword from "./pages/ResetPassword";
import Dashboard from "./pages/Dashboard";
import Account from "./pages/Account";
import Timeline from "./pages/Timeline";
import Unprocessed from "./pages/Unprocessed";
import Compare from "./pages/Compare";
import Statistics from "./pages/Statistics";
import Settings from "./pages/Settings";
import Datenschutz from "./pages/legal/Datenschutz";
import Impressum from "./pages/legal/Impressum";
import Agb from "./pages/legal/Agb";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/signup-success" element={<SignupSuccess />} />
      <Route path="/verify-email" element={<VerifyEmail />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/datenschutz" element={<Datenschutz />} />
      <Route path="/impressum" element={<Impressum />} />
      <Route path="/agb" element={<Agb />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route index element={<ClientRedirect />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="account" element={<Account />} />
          <Route path="clients/:clientId" element={<ClientShell />}>
            <Route path="timeline" element={<Timeline />} />
            <Route path="unprocessed" element={<Unprocessed />} />
            <Route path="compare" element={<Compare />} />
            <Route path="statistics" element={<Statistics />} />
            <Route path="settings" element={<Settings />} />
          </Route>
        </Route>
      </Route>
    </Routes>
  );
}
```

Beachte: die Kunden-Unterrouten sind jetzt relativ (`timeline` statt `clients/:clientId/timeline`), da sie unter der `clients/:clientId`-Elternroute verschachtelt sind — React Router löst das automatisch zu `/clients/:clientId/timeline` auf. `NavLink to="timeline"` in `ClientShell.tsx` (Task 4) funktioniert dadurch korrekt relativ zur aktuellen Route.

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler mehr.

- [ ] **Step 3: Manueller Rauchtest**

Run: `cd frontend && npm run dev` (falls nicht schon per anderem Terminal aktiv)

Öffne `http://localhost:5173`, logge dich ein, prüfe:
- Dashboard zeigt Header ohne "Dashboard"-Link-Aktivität-Bug (Link ist da, aber hervorgehoben/nicht klickbar)
- Klick auf einen Kunden zeigt die linke Navi + Mini-Header mit Kundenname
- Navi ist einklappbar (Toggle-Button), Zustand bleibt nach Seitenwechsel erhalten
- Auf schmalem Viewport (Browser-Fenster verkleinern) zeigt sich die mobile Variante mit Overlay

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: restructure App.tsx routes for nested AppShell/ClientShell layout"
```

---

## Part 3 — Seiten auf `PageHeader` umstellen

### Task 6: `Account.tsx` auf `PageHeader` umstellen

**Files:**
- Modify: `frontend/src/pages/Account.tsx`

- [ ] **Step 1: Read `Account.tsx` in full**

Finde den obersten `<h1>`/Überschriften-Block der Haupt-`Account`-Komponente (nicht der Unterkomponenten wie `DangerZoneSection`).

- [ ] **Step 2: `<h1>Account</h1>` durch `PageHeader` ersetzen**

Füge den Import hinzu: `import PageHeader from "../components/PageHeader";`

Ersetze das bisherige `<h1 className="...">Account</h1>` (exakter Wortlaut/Klassen können leicht abweichen — finde die Zeile, die den Seitentitel "Account" rendert) durch:

```tsx
<PageHeader title="Account" />
```

Der äußere Container-`<div className="max-w-xl space-y-6">` bleibt bestehen (Account ist bewusst schmaler als andere Seiten) — nur der `<h1>`-Teil wird ersetzt, nicht die ganze Struktur.

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Account.tsx
git commit -m "feat: migrate Account page to shared PageHeader"
```

---

### Task 7: `Timeline.tsx`, `Unprocessed.tsx` auf `PageHeader` umstellen

**Files:**
- Modify: `frontend/src/pages/Timeline.tsx`
- Modify: `frontend/src/pages/Unprocessed.tsx`

- [ ] **Step 1: Read beide Dateien in full**

Beide Seiten haben aktuell KEINEN expliziten Seitentitel im Sinne eines `<h1>` (Timeline zeigt direkt die Foto-Gruppen mit Pagination, Unprocessed direkt die Import-Queue) — die Kunden-Navi selbst (jetzt in `ClientShell`) und der Mini-Header übernehmen bisher implizit die Orientierung. Für Konsistenz mit den anderen Seiten (Compare/Statistics/Settings haben eigene Überschriften) fügt dieser Task einen `PageHeader` mit dem jeweiligen Seitennamen VOR den bestehenden Inhalt ein, OHNE die bestehende Logik/JSX-Struktur darunter zu verändern.

- [ ] **Step 2: `Timeline.tsx` anpassen**

Füge den Import hinzu: `import PageHeader from "../components/PageHeader";`

Finde den `return (` -Block der `export default function Timeline()`-Hauptkomponente (nicht die internen Unterkomponenten wie `TimelineWithLightbox`/`DayGroupSection`/`Lightbox`). Füge direkt nach der öffnenden Klammer des zurückgegebenen JSX, als erstes Kind, `<PageHeader title="Timeline" />` ein — der Rest des bestehenden JSX-Baums (Ladezustand, Fehlerzustand, `TimelineWithLightbox`-Aufruf etc.) bleibt unverändert erhalten, wird nur um dieses eine Element ergänzt.

- [ ] **Step 3: `Unprocessed.tsx` anpassen**

Gleiches Muster: Import hinzufügen, `<PageHeader title="Import" />` als erstes Kind im obersten zurückgegebenen JSX-Block der `export default function Unprocessed()`-Komponente einfügen.

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler.

- [ ] **Step 5: Manueller Check**

Run: `npm run dev`, navigiere zu Timeline und Import eines beliebigen Kunden, bestätige dass die Überschrift erscheint und der bestehende Inhalt (Fotos, Pagination, Import-Queue) weiterhin normal funktioniert.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Timeline.tsx frontend/src/pages/Unprocessed.tsx
git commit -m "feat: add PageHeader to Timeline and Unprocessed pages"
```

---

### Task 8: `Compare.tsx`, `Statistics.tsx`, `Settings.tsx` auf `PageHeader` umstellen

**Files:**
- Modify: `frontend/src/pages/Compare.tsx`
- Modify: `frontend/src/pages/Statistics.tsx`
- Modify: `frontend/src/pages/Settings.tsx`

- [ ] **Step 1: Read alle drei Dateien in full**

Diese drei Seiten haben vermutlich bereits eigene Überschriften-Elemente (unterschiedlich umgesetzt — das ist ja genau die zu behebende Inkonsistenz). Finde in jeder Datei die Stelle, die aktuell den Seitentitel rendert (z.B. ein `<h1>` oder eine `<h2>` am Anfang des zurückgegebenen JSX der jeweiligen `export default function`-Hauptkomponente).

- [ ] **Step 2: Jede der drei Überschriften durch `PageHeader` ersetzen**

Für jede Datei:
1. Füge `import PageHeader from "../components/PageHeader";` hinzu
2. Ersetze das gefundene Überschriften-Element durch `<PageHeader title="Compare" />` (bzw. `"Statistik"`, `"Settings"` für die jeweils andere Datei)
3. Falls die bisherige Überschrift zusätzliche Elemente daneben hatte (z.B. Buttons, Datums-Auswahl direkt neben dem Titel), nutze den `actions`-Prop von `PageHeader`, um sie beizubehalten: `<PageHeader title="Compare" actions={<>...bisherige Elemente...</>} />` — verändere dabei NICHT die Funktionalität dieser Elemente, nur ihre Einbettung.

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler.

- [ ] **Step 4: Manueller Check**

Run: `npm run dev`, prüfe alle drei Seiten für einen Kunden, bestätige einheitliche Überschriften-Optik und dass keine Funktionalität (Posen-Auswahl, Datumsbereich, Pose-CRUD) verloren ging.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Compare.tsx frontend/src/pages/Statistics.tsx frontend/src/pages/Settings.tsx
git commit -m "feat: unify Compare/Statistics/Settings page headers via PageHeader"
```

---

## Part 4 — Dashboard-Redesign

### Task 9: Dashboard — Suche, Geschlecht-Filter, modernere Karten

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: `Dashboard.tsx` vollständig ersetzen**

```tsx
// frontend/src/pages/Dashboard.tsx
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import PageHeader from "../components/PageHeader";
import type { Client } from "../types";

function ageFromBirthDate(birthDate: string | null): number | null {
  if (!birthDate) return null;
  return Math.floor(
    (Date.now() - new Date(birthDate).getTime()) / (365.25 * 24 * 60 * 60 * 1000)
  );
}

export default function Dashboard() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [heightCm, setHeightCm] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [gender, setGender] = useState("");
  const [startDate, setStartDate] = useState("");

  const [search, setSearch] = useState("");
  const [genderFilter, setGenderFilter] = useState("");

  const clientsQuery = useQuery({ queryKey: ["clients"], queryFn: api.clients.list });

  const createMutation = useMutation({
    mutationFn: () =>
      api.clients.create({
        name,
        height_cm: heightCm.trim() === "" ? null : Number(heightCm),
        birth_date: birthDate.trim() === "" ? null : birthDate,
        gender: gender.trim() === "" ? null : gender,
        start_date: startDate.trim() === "" ? null : startDate,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clients"] });
      setShowForm(false);
      setName("");
      setHeightCm("");
      setBirthDate("");
      setGender("");
      setStartDate("");
    },
  });

  const clients = clientsQuery.data ?? [];

  const availableGenders = useMemo(
    () => Array.from(new Set(clients.map((c) => c.gender).filter((g): g is string => !!g))),
    [clients]
  );

  const filteredClients = useMemo(() => {
    return clients.filter((c) => {
      const matchesSearch = c.name.toLowerCase().includes(search.trim().toLowerCase());
      const matchesGender = !genderFilter || c.gender === genderFilter;
      return matchesSearch && matchesGender;
    });
  }, [clients, search, genderFilter]);

  return (
    <div>
      <PageHeader
        title="Meine Kunden"
        actions={
          <button
            onClick={() => setShowForm((s) => !s)}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90"
          >
            Neuen Kunden anlegen
          </button>
        }
      />

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
            Körpergröße (cm)
            <input
              type="number"
              value={heightCm}
              onChange={(e) => setHeightCm(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Geburtsdatum
            <input
              type="date"
              value={birthDate}
              onChange={(e) => setBirthDate(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Geschlecht
            <input
              value={gender}
              onChange={(e) => setGender(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Startdatum
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <div className="flex items-end">
            <button
              type="submit"
              disabled={!name.trim() || createMutation.isPending}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-40"
            >
              {createMutation.isPending ? "Anlegen…" : "Anlegen"}
            </button>
          </div>
        </form>
      )}

      {clients.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-3">
          <input
            type="search"
            placeholder="Kunde suchen…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="min-w-[200px] flex-1 rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white focus:border-accent focus:outline-none"
          />
          {availableGenders.length > 0 && (
            <select
              value={genderFilter}
              onChange={(e) => setGenderFilter(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white focus:border-accent focus:outline-none"
            >
              <option value="">Alle Geschlechter</option>
              {availableGenders.map((g) => (
                <option key={g} value={g}>
                  {g}
                </option>
              ))}
            </select>
          )}
        </div>
      )}

      {clientsQuery.isLoading && <p className="text-slate-500">Lade…</p>}

      {!clientsQuery.isLoading && clients.length === 0 && (
        <div className="rounded-xl border border-dashed border-white/10 p-8 text-center text-slate-500">
          Noch keine Kunden — leg deinen ersten an.
        </div>
      )}

      {!clientsQuery.isLoading && clients.length > 0 && filteredClients.length === 0 && (
        <div className="rounded-xl border border-dashed border-white/10 p-8 text-center text-slate-500">
          Keine Kunden gefunden.
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {filteredClients.map((c) => (
          <DashboardClientCard key={c.id} client={c} />
        ))}
      </div>
    </div>
  );
}

function DashboardClientCard({ client: c }: { client: Client }) {
  const age = ageFromBirthDate(c.birth_date);
  const metaLine = [age ? `${age} Jahre` : null, c.height_cm ? `${c.height_cm} cm` : null]
    .filter(Boolean)
    .join(" · ");

  return (
    <Link
      to={`/clients/${c.id}/timeline`}
      className="rounded-xl border border-white/5 bg-surface p-4 transition-colors hover:border-accent/40"
    >
      <p className="text-base font-semibold text-white">{c.name}</p>
      <p className="mt-1 text-xs text-slate-500">{metaLine || "Keine Metriken hinterlegt"}</p>
      <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
        <span>{c.photo_count} Fotos</span>
        <span>
          {c.last_activity
            ? `Zuletzt: ${new Date(c.last_activity).toLocaleDateString("de-DE")}`
            : "Keine Fotos"}
        </span>
      </div>
    </Link>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler.

- [ ] **Step 3: Manueller Check**

Run: `npm run dev`, öffne `/dashboard`, prüfe:
- Suchfeld filtert die Kundenliste live
- Geschlecht-Filter-Dropdown erscheint nur, wenn mind. ein Kunde ein Geschlecht hinterlegt hat, und filtert korrekt
- Karten zeigen Fotoanzahl + letztes Aktivitätsdatum (bzw. "Keine Fotos")
- Leerer Zustand ("Noch keine Kunden…") erscheint korrekt, wenn keine Kunden existieren

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat: redesign Dashboard with search, gender filter, and richer client cards"
```

---

## Abschließende Verifikation

Nach Abschluss aller 9 Tasks:

- [ ] Volle Backend-Suite: `cd backend && .venv/Scripts/python -m pytest -v` — alle grün.
- [ ] Frontend-Typecheck: `cd frontend && npx tsc --noEmit` — keine Fehler.
- [ ] Manueller Durchlauf: Login → Dashboard (Header korrekt, kein aktiver "Dashboard"-Link mehr klickbar) → Kunde auswählen (Mini-Header + linke Navi erscheinen, einklappbar, Zustand bleibt über Seitenwechsel) → durch alle 5 Unterseiten klicken (Timeline/Import/Compare/Statistik/Settings) und bestätigen, dass Überschriften/Abstände einheitlich wirken → zurück zu Account (kein Navi-Sprung, "Dashboard"-Link im Header wieder da) → Fenster schmal ziehen und Kunden-Navi-Overlay-Verhalten prüfen.
