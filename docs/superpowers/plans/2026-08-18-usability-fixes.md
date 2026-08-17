# Usability-Fixes Runde 2 (Stufe 5d) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vier konkrete Usability-Fixes aus dem ersten echten Testlauf: Check-ins-Tab/Magic-Link/Reminder nur für Coach-Accounts, Gewichtseingabe akzeptiert Komma+Punkt (gerundet auf 0,05kg-Schritte), Upload-Fortschrittsanzeige, blockierendes Overlay beim Bulk-Assign.

**Architecture:** Neuer `parseWeightInput`-Helper (Frontend) + `parse_weight_kg`-Helper (Backend), gespiegelte Logik auf beiden Seiten. Neuer `BusyOverlayContext` (React Context) für die beiden Overlay-Fälle. Reine Sichtbarkeits-Filterung für Coach-only-Features, keine Datenmodell-Änderung.

**Tech Stack:** React/TypeScript, FastAPI/Pydantic, axios (`onUploadProgress`).

---

### Task 1: Coach-only Sichtbarkeit (Check-ins-Tab + Settings-Bereiche)

**Files:**
- Modify: `frontend/src/components/ClientShell.tsx`
- Modify: `frontend/src/pages/Settings.tsx`

- [ ] **Step 1: Check-ins-Tab nur für Coach-Accounts**

In `frontend/src/components/ClientShell.tsx`: `useCurrentUser` importieren und nutzen, `NAV_ITEMS` beim Rendern filtern statt direkt zu mappen.

```tsx
import { useCurrentUser } from "../hooks/useCurrentUser";
```

Im Komponentenkörper, nach der bestehenden `const { clientId } = useParams...`-Zeile:

```tsx
  const { data: user } = useCurrentUser();
  // Check-ins ist eine Coach<->Klient-Beziehungsfunktion - bei Single-
  // Accounts (die sich selbst tracken) ergibt der Tab keinen Sinn, siehe
  // Design-Spec "Usability-Fixes Runde 2" Abschnitt 1. Reine
  // Sichtbarkeits-Filterung, keine Datenlöschung - wechselt ein Account
  // später zum Coach, taucht der Tab sofort wieder auf.
  const visibleNavItems = NAV_ITEMS.filter(
    (item) => item.to !== "checkins" || user?.account_type === "coach"
  );
```

Beide `NAV_ITEMS.map(...)`-Vorkommen (Mobile-Overlay UND Desktop-Sidebar) auf `visibleNavItems.map(...)` umstellen. `activeNavTo` (nutzt aktuell `NAV_ITEMS.find(...)`) bleibt bei `NAV_ITEMS` (nicht `visibleNavItems`) - das bestimmt nur, welcher Tab als "aktiv" markiert wird, unabhängig von der Sichtbarkeit, das soll unverändert bleiben.

- [ ] **Step 2: Check-in-Link + Reminder in Settings.tsx nur für Coach-Accounts**

`isSingleAccount` existiert bereits. Der Check-in-Link-Block (`<div data-tour="settings-checkin-link">...</div>`, inkl. dem "Regenerate link"-Button) wird komplett in `{!isSingleAccount && (...)}` gewrappt - aktuell ist er unconditional. Das Reminder-Feld (`<label>...Remind me after X days...</label>` Block, inkl. dem "The reminder is sent to..."-Hinweistext direkt darunter) wird ebenfalls in `{!isSingleAccount && (...)}` gewrappt - aktuell wird es IMMER gezeigt (nur die Beschriftung ändert sich je nach Single/Coach).

Konkret: das gesamte Formular-Innere zwischen `<form onSubmit=...>` und `</form>` wird für Single-Accounts nur noch die (unveränderte) `updateClientMutation`-Logik im Hintergrund behalten, aber im JSX nichts mehr rendern außer optional den Submit-Button auch weglassen, DA es für Single-Accounts nichts mehr zu speichern gibt in diesem Formular (kein Reminder-Feld, kein E-Mail-Feld, keine Notiz mehr sichtbar). Am saubersten: das komplette `<form>...</form>`-Element in `{!isSingleAccount && (<form>...</form>)}` wrappen, und den äußeren `<div className="space-y-4 rounded-xl ...">`-Container ebenfalls nur rendern, wenn er tatsächlich Inhalt hat:

```tsx
      {!isSingleAccount && (
        <div className="space-y-4 rounded-xl border border-white/5 bg-surface p-4">
          <div data-tour="settings-checkin-link">
            {/* ... unverändert: Check-in-Link-Block ... */}
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              updateClientMutation.mutate();
            }}
            className="space-y-3 border-t border-white/5 pt-4"
          >
            <label className="flex flex-col gap-1 text-sm text-slate-400">
              Client's email (for reminders)
              <input
                type="email"
                value={clientEmail}
                onChange={(e) => setClientEmail(e.target.value)}
                className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-slate-400">
              Reminder after X days without a check-in (blank = no reminder)
              <input
                type="number"
                min={1}
                value={reminderDays}
                onChange={(e) => setReminderDays(e.target.value)}
                className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-slate-400">
              Private note (visible only to you)
              <textarea
                value={coachNote}
                onChange={(e) => setCoachNote(e.target.value)}
                rows={3}
                className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
              />
            </label>
            <button
              type="submit"
              disabled={updateClientMutation.isPending}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-50"
            >
              {updateClientMutation.isPending ? "Saving…" : "Save"}
            </button>
          </form>
        </div>
      )}
```

Da das Formular jetzt nur noch für Coach-Accounts existiert, entfällt die bisherige `isSingleAccount`-Verzweigung INNERHALB der `updateClientMutation` (die `...(isSingleAccount ? {} : {...})`-Spread-Logik) - vereinfachen zu direktem Objekt, da `updateClientMutation` jetzt gar nicht mehr aufrufbar ist, wenn `isSingleAccount` true ist:

```tsx
  const updateClientMutation = useMutation({
    mutationFn: () =>
      api.clients.update(clientIdNum, {
        coach_private_note: coachNote.trim() === "" ? null : coachNote,
        email: clientEmail.trim() === "" ? null : clientEmail.trim(),
        checkin_reminder_days: reminderDays.trim() === "" ? null : Number(reminderDays),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["clients", clientIdNum] }),
  });
```

Die `checkinLink`-Variable und der `regenerateTokenMutation`/`copyFeedback`-State bleiben unverändert bestehen (werden nur nicht mehr gerendert, wenn `isSingleAccount`).

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler

- [ ] **Step 4: Manuell prüfen**

Mit einem Single-Account einloggen: kein "Check-ins"-Tab in der Sidebar, Settings-Seite zeigt nur noch den "Poses"-Block. Mit einem Coach-Account: alles wie bisher sichtbar.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ClientShell.tsx frontend/src/pages/Settings.tsx
git commit -m "feat: hide check-ins tab and coach-only settings for single accounts"
```

---

### Task 2: Gewichts-Parsing-Helper (Frontend + Backend)

**Files:**
- Create: `frontend/src/utils/weight.ts`
- Create: `backend/app/utils/weight.py`
- Test: `backend/tests/test_weight_utils.py`

- [ ] **Step 1: Frontend-Helper**

```ts
// frontend/src/utils/weight.ts

/** Parst eine Gewichts-Nutzereingabe (Komma ODER Punkt als
 * Dezimaltrennzeichen, z.B. "76,05" oder "76.05") zu einer Zahl,
 * gerundet auf die naechsten 0,05 kg - siehe Design-Spec
 * "Usability-Fixes Runde 2" Abschnitt 2. Gibt null bei leerem Input
 * zurueck (== "kein Wert eingegeben"), NaN bei tatsaechlich ungueltigem
 * Input (Aufrufer soll das von "kein Wert" unterscheiden koennen). */
export function parseWeightInput(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  const normalized = trimmed.replace(",", ".");
  const value = Number(normalized);
  if (!Number.isFinite(value)) return NaN;
  return Math.round(value / 0.05) * 0.05;
}
```

- [ ] **Step 2: Backend-Helper**

```python
# backend/app/utils/weight.py
"""Gespiegelte Logik zu frontend/src/utils/weight.ts - Komma/Punkt als
Dezimaltrennzeichen tolerieren, auf 0,05kg-Schritte runden. Siehe
Design-Spec "Usability-Fixes Runde 2" Abschnitt 2. Als Defensive-
Maßnahme gedacht (v.a. für Endpunkte, die direkt per API ohne unser
Frontend aufgerufen werden koennten) - das Frontend normalisiert schon
selbst, bevor es sendet."""


def parse_weight_kg(value: float | str | None) -> float | None:
    """Akzeptiert float, int, oder String mit Komma/Punkt. Gibt None bei
    None/leerem String zurueck. Wirft ValueError bei nicht parsbarem
    String (Aufrufer entscheidet, wie das dem Nutzer gemeldet wird)."""
    if value is None:
        return None
    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed == "":
            return None
        value = float(trimmed.replace(",", "."))
    return round(float(value) / 0.05) * 0.05
```

- [ ] **Step 3: Backend-Tests**

```python
# backend/tests/test_weight_utils.py
import pytest

from app.utils.weight import parse_weight_kg


def test_parses_float_directly():
    assert parse_weight_kg(76.05) == 76.05


def test_parses_comma_string():
    assert parse_weight_kg("76,05") == 76.05


def test_parses_dot_string():
    assert parse_weight_kg("76.05") == 76.05


def test_rounds_to_nearest_0_05():
    assert parse_weight_kg("76.03") == 76.05
    assert parse_weight_kg("76.01") == 76.0


def test_none_and_empty_string_return_none():
    assert parse_weight_kg(None) is None
    assert parse_weight_kg("") is None
    assert parse_weight_kg("   ") is None


def test_invalid_string_raises_value_error():
    with pytest.raises(ValueError):
        parse_weight_kg("not a number")
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest -q tests/test_weight_utils.py`
Expected: alle PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/weight.ts backend/app/utils/weight.py backend/tests/test_weight_utils.py
git commit -m "feat: add weight input parsing helper (comma/dot, 0.05kg rounding)"
```

---

### Task 3: Gewichts-Inputs im Frontend umstellen

**Files:**
- Modify: `frontend/src/pages/Timeline.tsx` (`WeightEditor`)
- Modify: `frontend/src/pages/Unprocessed.tsx`
- Modify: `frontend/src/pages/CheckinSubmit.tsx`

- [ ] **Step 1: Timeline.tsx `WeightEditor`**

Import ergänzen: `import { parseWeightInput } from "../utils/weight";`

Den Input von `type="number" step="0.1"` auf `type="text" inputMode="decimal"` umstellen:

```tsx
      <input
        type="text"
        inputMode="decimal"
        autoFocus
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="kg"
        className="w-20 rounded-lg border border-white/10 bg-black/30 px-2 py-1 text-sm text-white placeholder:text-slate-600 focus:border-accent focus:outline-none"
      />
```

Die `mutation`-`mutationFn` nutzt aktuell `Number(value)` direkt - umstellen auf `parseWeightInput(value)`:

```tsx
  const mutation = useMutation({
    mutationFn: () => {
      const parsed = parseWeightInput(value);
      return api.dayLogs.upsert(clientId, {
        date,
        weight_kg: parsed === null || Number.isNaN(parsed) ? null : parsed,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["day-logs", clientId] });
      setEditing(false);
    },
  });
```

(Ein tatsächlich ungültiger, nicht-leerer Wert wie "abc" wird hier bewusst still als `null` behandelt statt eine Fehlermeldung zu zeigen - das entspricht dem bisherigen Verhalten von `Number("abc")` (das zu `NaN` und damit implizit auch zu keinem sinnvollen Wert führte); eine explizite Fehlermeldung für ungültige Eingaben ist nicht Teil dieses Tasks.)

- [ ] **Step 2: Unprocessed.tsx**

Import ergänzen: `import { parseWeightInput } from "../utils/weight";`

Den Tages-Gewicht-Input von `type="number" step="0.1"` auf `type="text" inputMode="decimal"` umstellen (Zeile mit `placeholder="kg, optional"`).

Die `weightForDate`-Funktion nutzt aktuell `Number(raw)` - umstellen:

```tsx
  function weightForDate(date: string): number | null {
    const raw = weightByDate[date] ?? "";
    const parsed = parseWeightInput(raw);
    return parsed === null || Number.isNaN(parsed) ? null : parsed;
  }
```

Die einzelne "Einzeln zuordnen"-Zuordnung (`assignMutation.mutate({..., weight: weightByDate[group.date] ?? ""})`) übergibt den Rohstring an `assignMutation`, deren `mutationFn` selbst `weight.trim() === "" ? null : Number(weight)` macht - dort ebenfalls auf `parseWeightInput` umstellen:

```tsx
  const assignMutation = useMutation({
    mutationFn: ({ id, poseId, weight }: { id: number; poseId: number; weight: string }) => {
      const parsed = parseWeightInput(weight);
      return api.photos.assign(clientIdNum, id, {
        pose_id: poseId,
        weight_kg: parsed === null || Number.isNaN(parsed) ? null : parsed,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["photos", clientIdNum] });
      queryClient.invalidateQueries({ queryKey: ["day-logs", clientIdNum] });
    },
  });
```

- [ ] **Step 3: CheckinSubmit.tsx**

Import ergänzen: `import { parseWeightInput } from "../utils/weight";`

Den Gewicht-Input von `type="number" step="0.1"` auf `type="text" inputMode="decimal"` umstellen.

`submitMutation`s `mutationFn` nutzt aktuell `weightKg.trim() === "" ? null : Number(weightKg)` - umstellen:

```tsx
  const submitMutation = useMutation({
    mutationFn: () => {
      const parsed = parseWeightInput(weightKg);
      return api.publicCheckin.submit(token!, {
        weight_kg: parsed === null || Number.isNaN(parsed) ? null : parsed,
        client_note: note.trim() === "" ? undefined : note.trim(),
        files,
      });
    },
    onSuccess: () => {
      setWeightKg("");
      setNote("");
      setFiles([]);
      queryClient.invalidateQueries({ queryKey: ["public-checkin", token] });
    },
  });
```

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler

- [ ] **Step 5: Manuell prüfen**

In einem der drei Formulare "76,05" eingeben und speichern - Wert sollte als `76.05` gespeichert werden (in der Timeline/Statistics-Anzeige nachprüfen).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Timeline.tsx frontend/src/pages/Unprocessed.tsx frontend/src/pages/CheckinSubmit.tsx
git commit -m "feat: accept comma or dot in weight inputs across the app"
```

---

### Task 4: Backend-Defensive für Gewichtswerte

**Files:**
- Modify: `backend/app/schemas/day_log.py`
- Modify: `backend/app/schemas/photo.py`
- Modify: `backend/app/routers/public_checkin.py`
- Test: `backend/tests/test_day_logs_router_scoped.py`, `backend/tests/test_photos_router_scoped.py`, `backend/tests/test_public_checkin_router.py`

- [ ] **Step 1: `DayLogUpsert` toleriert Komma-Strings**

In `backend/app/schemas/day_log.py`:

```python
from datetime import date as date_

from pydantic import BaseModel, field_validator

from app.utils.weight import parse_weight_kg


class DayLogUpsert(BaseModel):
    date: date_
    weight_kg: float | None = None
    notes: str | None = None

    @field_validator("weight_kg", mode="before")
    @classmethod
    def _parse_weight(cls, v):
        if v is None or isinstance(v, (int, float)):
            return v
        try:
            return parse_weight_kg(v)
        except ValueError:
            raise ValueError("weight_kg must be a number (comma or dot as decimal separator)")


class DayLogOut(BaseModel):
    id: int
    date: date_
    weight_kg: float | None
    notes: str | None

    class Config:
        from_attributes = True
```

- [ ] **Step 2: `PhotoAssign`/`PhotoBulkAssignItem` toleriert Komma-Strings**

In `backend/app/schemas/photo.py`, Import ergänzen: `from pydantic import BaseModel, computed_field, field_validator` und `from app.utils.weight import parse_weight_kg`. Beiden Klassen denselben Validator hinzufügen (identischer Code wie oben, daher als kleiner privater Mixin sauberer):

```python
class _WeightValidatorMixin:
    @field_validator("weight_kg", mode="before")
    @classmethod
    def _parse_weight(cls, v):
        if v is None or isinstance(v, (int, float)):
            return v
        try:
            return parse_weight_kg(v)
        except ValueError:
            raise ValueError("weight_kg must be a number (comma or dot as decimal separator)")


class PhotoAssign(BaseModel, _WeightValidatorMixin):
    pose_id: int
    weight_kg: float | None = None


class PhotoBulkAssignItem(_WeightValidatorMixin, BaseModel):
    photo_id: int
    pose_id: int
    weight_kg: float | None = None
```

(Reihenfolge der Basisklassen bei `PhotoBulkAssignItem` bewusst mit Mixin zuerst - Pydantic-Validatoren aus Mixins werden nur zuverlässig erkannt, wenn der Mixin vor `BaseModel` in der MRO steht; bei `PhotoAssign` oben zur Konsistenz genauso machen, also eigentlich beide als `class X(_WeightValidatorMixin, BaseModel):` - im Code entsprechend vereinheitlichen.)

- [ ] **Step 3: Public-Checkin-Endpoint (Form-Parameter, kein Pydantic-Model)**

In `backend/app/routers/public_checkin.py`: Import ergänzen `from app.utils.weight import parse_weight_kg`. Den Funktionsparameter ändern von:
```python
    weight_kg: float | None = Form(default=None),
```
zu:
```python
    weight_kg: str | None = Form(default=None),
```
Direkt am Anfang der Funktion (nach den bestehenden `MAX_FILES_PER_SUBMISSION`/Dateigröße-Validierungen, vor dem `CheckinSubmission(...)`-Erzeugen) den Rohwert parsen:
```python
    try:
        parsed_weight_kg = parse_weight_kg(weight_kg)
    except ValueError:
        raise HTTPException(400, "Weight must be a number (comma or dot as decimal separator)")
```
Alle weiteren Verwendungen von `weight_kg` in der Funktion (aktuell: `CheckinSubmission(..., weight_kg=weight_kg, ...)`, die `if weight_kg is not None or client_note:`-Bedingung, und `day_log.weight_kg = weight_kg`) auf `parsed_weight_kg` umstellen.

- [ ] **Step 4: Tests ergänzen**

In `backend/tests/test_day_logs_router_scoped.py`: neuer Test, der `PUT /clients/{id}/day-logs` mit `"weight_kg": "76,05"` (als String im JSON-Body) aufruft und `76.05` als gespeicherten Wert erwartet.

In `backend/tests/test_photos_router_scoped.py`: neuer Test für `POST /clients/{id}/photos/{photo_id}/assign` mit `"weight_kg": "76,05"`.

In `backend/tests/test_public_checkin_router.py`: neuer Test für `POST /public/checkin/{token}/submit` mit Form-Daten `weight_kg="76,05"`, erwartet `76.05` im Response bzw. im erzeugten `DayLog`.

(Exakte Test-Helper/Fixtures aus den bestehenden Tests der jeweiligen Datei übernehmen, nicht neu erfinden.)

- [ ] **Step 5: Volle Backend-Testsuite laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: alle Tests grün (bis auf den bekannten, unabhängigen `test_gemini_key_is_scoped_per_account`-Fall)

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/day_log.py backend/app/schemas/photo.py backend/app/routers/public_checkin.py backend/tests/test_day_logs_router_scoped.py backend/tests/test_photos_router_scoped.py backend/tests/test_public_checkin_router.py
git commit -m "feat: tolerate comma decimal separator in weight_kg on backend"
```

---

### Task 5: `BusyOverlayContext` + `BusyOverlay`-Komponente

**Files:**
- Create: `frontend/src/contexts/BusyOverlayContext.tsx`
- Create: `frontend/src/components/BusyOverlay.tsx`

- [ ] **Step 1: Context**

```tsx
// frontend/src/contexts/BusyOverlayContext.tsx
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

interface BusyOverlayState {
  active: boolean;
  label: string;
  progressPercent: number | null; // null = kein Fortschrittsbalken, nur Spinner+Label
}

interface BusyOverlayContextValue extends BusyOverlayState {
  show: (label: string, progressPercent?: number | null) => void;
  updateProgress: (progressPercent: number) => void;
  hide: () => void;
}

const BusyOverlayContext = createContext<BusyOverlayContextValue | null>(null);

/** App-weites blockierendes Overlay fuer laengere Aktionen (Upload,
 * Bulk-Save) - siehe Design-Spec "Usability-Fixes Runde 2" Abschnitt 3+4.
 * Bewusst KEIN Abbrechen-Button (siehe Design-Entscheidung). */
export function BusyOverlayProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<BusyOverlayState>({
    active: false,
    label: "",
    progressPercent: null,
  });

  const show = useCallback((label: string, progressPercent: number | null = null) => {
    setState({ active: true, label, progressPercent });
  }, []);

  const updateProgress = useCallback((progressPercent: number) => {
    setState((s) => ({ ...s, progressPercent }));
  }, []);

  const hide = useCallback(() => {
    setState({ active: false, label: "", progressPercent: null });
  }, []);

  return (
    <BusyOverlayContext.Provider value={{ ...state, show, updateProgress, hide }}>
      {children}
    </BusyOverlayContext.Provider>
  );
}

export function useBusyOverlay() {
  const ctx = useContext(BusyOverlayContext);
  if (!ctx) throw new Error("useBusyOverlay must be used within BusyOverlayProvider");
  return ctx;
}
```

- [ ] **Step 2: Overlay-Komponente**

```tsx
// frontend/src/components/BusyOverlay.tsx
import { useBusyOverlay } from "../contexts/BusyOverlayContext";

/** Rendert nichts, solange kein Vorgang aktiv ist. Vollbild, blockiert
 * komplett (kein pointer-events durch, kein Escape) - siehe Design-Spec
 * "Usability-Fixes Runde 2" Abschnitt 3+4. */
export function BusyOverlay() {
  const { active, label, progressPercent } = useBusyOverlay();
  if (!active) return null;

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/70">
      <div className="w-full max-w-xs space-y-3 rounded-xl border border-white/10 bg-surface p-6 text-center shadow-2xl">
        <p className="text-sm font-medium text-white">{label}</p>
        {progressPercent !== null ? (
          <div className="space-y-1">
            <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
              <div
                className="h-full rounded-full bg-accent transition-all duration-150"
                style={{ width: `${Math.max(0, Math.min(100, progressPercent))}%` }}
              />
            </div>
            <p className="text-xs text-slate-400">{Math.round(progressPercent)}%</p>
          </div>
        ) : (
          <div className="mx-auto h-6 w-6 animate-spin rounded-full border-2 border-white/20 border-t-accent" />
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler (noch nicht eingebunden)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/contexts/BusyOverlayContext.tsx frontend/src/components/BusyOverlay.tsx
git commit -m "feat: add BusyOverlay context and component"
```

---

### Task 6: Einbindung - Upload-Fortschritt + Save-all-Overlay

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/Unprocessed.tsx`

- [ ] **Step 1: `BusyOverlayProvider` + `BusyOverlay` in App.tsx einbinden**

Analog zu `OnboardingProvider`/`OnboardingModalGate` (siehe `App.tsx` aus Stufe 5b): Import ergänzen, `BusyOverlayProvider` um die bestehende `OnboardingProvider`-Struktur legen (Reihenfolge der beiden Provider zueinander ist egal, keine Abhängigkeit), `<BusyOverlay />` neben `<OnboardingModalGate />` rendern:

```tsx
import { BusyOverlayProvider } from "./contexts/BusyOverlayContext";
import { BusyOverlay } from "./components/BusyOverlay";
```

```tsx
export default function App() {
  return (
    <BusyOverlayProvider>
      <OnboardingProvider>
        <Routes>
          {/* ... unverändert ... */}
        </Routes>
        <OnboardingModalGate />
      </OnboardingProvider>
      <BusyOverlay />
    </BusyOverlayProvider>
  );
}
```

- [ ] **Step 2: `api.photos.upload` bekommt optionalen Progress-Callback**

In `frontend/src/api/client.ts`, die bestehende `upload`-Methode erweitern:

```tsx
    upload: (clientId: number, files: File[], onUploadProgress?: (percent: number) => void) => {
      const form = new FormData();
      for (const file of files) form.append("files", file);
      return client
        .post<UnprocessedPhoto[]>(`/clients/${clientId}/photos/upload`, form, {
          headers: { "Content-Type": "multipart/form-data" },
          onUploadProgress: onUploadProgress
            ? (e) => {
                if (e.total) onUploadProgress(Math.round((e.loaded / e.total) * 100));
              }
            : undefined,
        })
        .then((r) => r.data);
    },
```

- [ ] **Step 3: `Unprocessed.tsx` nutzt das Overlay für Upload und Bulk-Assign**

Import ergänzen: `import { useBusyOverlay } from "../contexts/BusyOverlayContext";`

Im Komponentenkörper: `const { show, updateProgress, hide } = useBusyOverlay();`

`uploadMutation` umstellen, um den Progress-Callback durchzureichen und das Overlay zu steuern:

```tsx
  const uploadMutation = useMutation({
    mutationFn: (files: File[]) => {
      show("Uploading photos…", 0);
      return api.photos.upload(clientIdNum, files, (percent) => updateProgress(percent));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["photos", clientIdNum] });
      hide();
    },
    onError: () => hide(),
  });
```

`bulkAssignMutation` umstellen (kein Fortschrittsbalken, nur Label):

```tsx
  const bulkAssignMutation = useMutation({
    mutationFn: (items: { photo_id: number; pose_id: number; weight_kg: number | null }[]) => {
      show("Saving…");
      return api.photos.assignBulk(clientIdNum, items);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["photos", clientIdNum] });
      queryClient.invalidateQueries({ queryKey: ["day-logs", clientIdNum] });
      hide();
    },
    onError: () => hide(),
  });
```

Die bestehenden `uploadMutation.isPending`/`bulkAssignMutation.isPending`-Checks in den Button-`disabled`/Label-Props bleiben unverändert bestehen (zusätzliche, nicht widersprüchliche Absicherung neben dem Overlay).

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler

- [ ] **Step 5: Manuell prüfen**

Mehrere Fotos hochladen: Vollbild-Overlay mit Fortschrittsbalken erscheint, zählt hoch, verschwindet nach Abschluss. "Save all assigned" klicken: Overlay mit "Saving…" erscheint sofort, blockiert Interaktion, verschwindet nach Abschluss.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.tsx frontend/src/api/client.ts frontend/src/pages/Unprocessed.tsx
git commit -m "feat: show busy overlay with progress during upload and bulk-assign"
```

---

### Task 7: Finaler Review + Branch abschließen

- [ ] **Step 1: Vollständigen Typecheck laufen lassen**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler

- [ ] **Step 2: Backend-Testsuite laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: alle Tests grün (bis auf den bekannten, unabhängigen `test_gemini_key_is_scoped_per_account`-Fall)

- [ ] **Step 3: Manuelle Gesamt-Durchsicht**

Single-Account: kein Check-ins-Tab, keine Magic-Link/Reminder-Settings. Coach-Account: alles wie bisher. Gewichtseingabe mit Komma an allen 3 Stellen (Timeline, Unprocessed, öffentlicher Check-in). Upload-Fortschrittsanzeige. Save-all-Overlay.

- [ ] **Step 4: `superpowers:finishing-a-development-branch` nutzen**

Tests verifizieren (bereits in Step 1/2 geschehen), Merge nach `dev` anbieten (inkl. Push nach origin), danach `dev`→`main` nur nach expliziter Nutzer-Bestätigung.
