# Coach Onboarding Tour v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the click-blocking bug in the coach onboarding tour, extend it to cover all core product areas (client settings, magic link, poses, check-in review), add a tour-end keep/delete choice for the client created during the tour, and replace the "Add New Client" inline form with a modal (3 simplified fields, Save/Cancel, spinner, success message) — backed by a new general-purpose client-deletion feature.

**Architecture:** Client deletion is a new backend endpoint (`DELETE /api/clients/{client_id}`) reusing the existing file-cleanup logic (extracted into a shared `services/photo_files.py` so both `routers/photos.py` and `routers/clients.py` use one implementation) plus DB-level cascade deletes already configured on every child table's foreign key. The tour itself gets a bug fix (CSS pointer-events), more `data-tour` anchors, an extended step list, and a new `"end"` phase with its own modal component. The Add-Client form becomes its own modal component reused both from the Dashboard button and (implicitly) from the tour's first step.

**Tech Stack:** FastAPI + SQLAlchemy (backend), React + TanStack Query + TypeScript + Tailwind (frontend), pytest for backend tests, `npx tsc --noEmit` + manual browser check for frontend (no frontend test framework in this repo).

---

### Task 1: Backend — client deletion endpoint

**Files:**
- Create: `backend/app/services/photo_files.py`
- Modify: `backend/app/routers/photos.py`
- Modify: `backend/app/routers/clients.py`
- Test: `backend/tests/test_clients_router.py`

- [ ] **Step 1: Extract the shared file-cleanup helper**

Write `backend/app/services/photo_files.py`:

```python
"""Datei-Cleanup für Fotos - gemeinsam genutzt von routers/photos.py
(Einzel-/Tages-Löschung) und routers/clients.py (Komplett-Löschung eines
Klienten, siehe Design-Spec "Coach-Onboarding-Tour v2" Teil 4)."""
from app.core.config import settings
from app.models.photo import Photo
from app.services.storage_sync import delete_remote, ensure_local


def delete_photo_files(photo: Photo) -> None:
    """Entfernt alle mit dem Foto verknüpften Dateien von der Platte
    (Original, HEIC-Vorschau, normalisierte Version, Thumbnail).
    Fehlende Dateien werden stillschweigend übersprungen (z.B. bei
    inkonsistentem Zustand)."""
    for rel_path in (photo.original_path, photo.preview_path, photo.normalized_path, photo.thumbnail_path):
        if not rel_path:
            continue
        ensure_local(rel_path)
        file = settings.data_dir / rel_path
        if file.exists():
            file.unlink()
        delete_remote(rel_path)
```

- [ ] **Step 2: Update `routers/photos.py` to use the shared helper**

In `backend/app/routers/photos.py`, remove the local `_delete_photo_files` function definition (currently right before `delete_photos_by_date`):

```python
def _delete_photo_files(photo: Photo) -> None:
    """Entfernt alle mit dem Foto verknüpften Dateien von der Platte
    (Original, HEIC-Vorschau, normalisierte Version). Fehlende Dateien
    werden stillschweigend übersprungen (z.B. bei inkonsistentem Zustand)."""
    for rel_path in (photo.original_path, photo.preview_path, photo.normalized_path, photo.thumbnail_path):
        if not rel_path:
            continue
        ensure_local(rel_path)
        file = settings.data_dir / rel_path
        if file.exists():
            file.unlink()
        delete_remote(rel_path)
```

Replace it with an import at the top of the file (add alongside the existing `from app.services.storage_sync import delete_remote, ensure_local, push` line):

```python
from app.services.photo_files import delete_photo_files as _delete_photo_files
```

This keeps every existing call site (`_delete_photo_files(photo)`, used in `delete_photos_by_date` and `delete_photo`) working unchanged — only the definition moved.

- [ ] **Step 3: Run the existing photo tests to confirm the refactor didn't break anything**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_photos_router.py tests/test_photos_router_scoped.py -v`
Expected: all pass (find the exact test file names first with `ls backend/tests/test_photo*` if these names don't match exactly).

- [ ] **Step 4: Write the failing test for client deletion**

Append to `backend/tests/test_clients_router.py`:

```python
def test_delete_client_removes_client_and_cascades(client, db_session, tmp_path, monkeypatch):
    from app.core.config import settings
    from app.models.client import Client
    from app.models.photo import Photo, ProcessingStatus
    from app.models.pose import Pose

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    _login(client, db_session)

    create_resp = client.post("/api/clients", json={"name": "To Delete"})
    client_id = create_resp.json()["id"]

    client_row = db_session.get(Client, client_id)
    pose = Pose(client_id=client_id, name="Front", sort_order=0)
    db_session.add(pose)
    db_session.commit()
    db_session.refresh(pose)

    photo_dir = tmp_path / "photos_processed" / str(client_id)
    photo_dir.mkdir(parents=True)
    photo_file = photo_dir / "a.jpg"
    photo_file.write_bytes(b"fake-jpeg-bytes")
    photo = Photo(
        client_id=client_id,
        filename="a.jpg",
        original_path=f"photos_processed/{client_id}/a.jpg",
        taken_at=datetime.now(timezone.utc),
        status=ProcessingStatus.PROCESSED,
        pose_id=pose.id,
    )
    db_session.add(photo)
    db_session.commit()

    response = client.delete(f"/api/clients/{client_id}")
    assert response.status_code == 204

    assert db_session.get(Client, client_id) is None
    assert not photo_file.exists()

    list_resp = client.get("/api/clients")
    assert list_resp.json() == []


def test_delete_client_requires_ownership(client, db_session):
    owner_a = _login(client, db_session, email="owner-a@example.com", password="pw12345")
    create_resp = client.post("/api/clients", json={"name": "Owner A's Client"})
    client_id = create_resp.json()["id"]

    client.post("/api/auth/logout")
    _login(client, db_session, email="owner-b@example.com", password="pw12345")
    response = client.delete(f"/api/clients/{client_id}")
    assert response.status_code == 404
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_clients_router.py -k delete -v`
Expected: FAIL — 405 Method Not Allowed (no DELETE route exists yet).

- [ ] **Step 6: Implement the endpoint**

In `backend/app/routers/clients.py`, add this import (extend the existing imports section):

```python
from app.models.photo import Photo
from app.services.photo_files import delete_photo_files
```

Add the endpoint at the end of the file:

```python
@router.delete("/{client_id}", status_code=204)
def delete_client(client_row: Client = Depends(get_owned_client), db: Session = Depends(get_db)):
    """Löscht einen Klienten unwiderruflich inkl. aller Datei-Assets
    seiner Fotos - siehe Design-Spec "Coach-Onboarding-Tour v2" Teil 4.
    Die Datenbank-Zeilen der abhängigen Tabellen (Photos, Poses, DayLogs,
    CheckinSubmissions) werden automatisch durch ON DELETE CASCADE auf
    dem jeweiligen Foreign Key entfernt (siehe core/database.py, PRAGMA
    foreign_keys=ON für SQLite, nativ auf Postgres) - hier muss nur noch
    das Löschen der Dateien auf Platte/R2 explizit passieren, das kann
    die Datenbank nicht selbst."""
    photos = db.query(Photo).filter(Photo.client_id == client_row.id).all()
    for photo in photos:
        delete_photo_files(photo)
    db.delete(client_row)
    db.commit()
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_clients_router.py -v`
Expected: all pass.

- [ ] **Step 8: Run the full backend suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all pass aside from the known unrelated flaky `test_gemini_key_is_scoped_per_account`.

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/photo_files.py backend/app/routers/photos.py backend/app/routers/clients.py backend/tests/test_clients_router.py
git commit -m "feat: add client deletion endpoint with cascading file cleanup"
```

---

### Task 2: Frontend — fix the tour's click-blocking bug

**Files:**
- Modify: `frontend/src/components/OnboardingTooltip.tsx`

- [ ] **Step 1: Add `pointer-events-none`/`pointer-events-auto`**

In `frontend/src/components/OnboardingTooltip.tsx`, find:

```tsx
  return (
    <div className="fixed inset-0 z-[100]">
```

Replace with:

```tsx
  return (
    <div className="pointer-events-none fixed inset-0 z-[100]">
```

Find the tooltip bubble div:

```tsx
          <div
            className="fixed z-[101] w-72 rounded-xl border border-accent/30 bg-surface p-4 shadow-2xl transition-all duration-300"
```

Replace with (adds `pointer-events-auto` so the Skip/Next buttons inside it stay clickable):

```tsx
          <div
            className="pointer-events-auto fixed z-[101] w-72 rounded-xl border border-accent/30 bg-surface p-4 shadow-2xl transition-all duration-300"
```

- [ ] **Step 2: Verify the frontend type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/OnboardingTooltip.tsx
git commit -m "fix: tour overlay no longer blocks clicks on the rest of the page"
```

---

### Task 3: Frontend — extend the tour's step list and anchors

**Files:**
- Modify: `frontend/src/contexts/OnboardingContext.tsx`
- Modify: `frontend/src/pages/Settings.tsx`
- Modify: `frontend/src/pages/ClientCheckins.tsx`
- Modify: `frontend/src/components/OnboardingModal.tsx`

- [ ] **Step 1: Add the two missing `data-tour` anchors**

In `frontend/src/pages/Settings.tsx`, find the "Add pose" form:

```tsx
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (newPoseName.trim()) createMutation.mutate(newPoseName.trim());
          }}
          className="mt-4 flex gap-2 border-t border-white/5 pt-4"
        >
```

Replace with (adds the anchor):

```tsx
        <form
          data-tour="settings-add-pose"
          onSubmit={(e) => {
            e.preventDefault();
            if (newPoseName.trim()) createMutation.mutate(newPoseName.trim());
          }}
          className="mt-4 flex gap-2 border-t border-white/5 pt-4"
        >
```

In `frontend/src/pages/ClientCheckins.tsx`, find the component's root returned `<div>` (read the file to locate its exact current className/structure — it wraps `<PageHeader title="Check-ins" />` and the checkins list below it) and add `data-tour="checkins-review-area"` to that root div. Read the file fully first to find the exact JSX before editing — don't guess at the structure.

- [ ] **Step 2: Replace `COACH_STEPS` with the extended list**

In `frontend/src/contexts/OnboardingContext.tsx`, replace:

```tsx
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
```

with:

```tsx
export const COACH_STEPS: TourStep[] = [
  {
    id: "new-client",
    dataTour: "dashboard-new-client",
    title: "Add your first client",
    body: "This is where you add a new client to start tracking their progress.",
  },
  {
    id: "client-settings",
    dataTour: "nav-settings",
    title: "Client settings",
    body: "Every client has their own settings page - profile info, check-in reminders, and the magic link (next step).",
  },
  {
    id: "magic-link",
    dataTour: "settings-checkin-link",
    title: "The magic link",
    body: "This link lets your client submit weight and progress photos without creating an account. Copy it and send it to them - it stays valid permanently, and you can regenerate it here if needed.",
  },
  {
    id: "add-pose",
    dataTour: "settings-add-pose",
    title: "Create a pose",
    body: "Poses are the angles you photograph (e.g. Front, Side, Back) - they're the fixed reference points for before/after comparisons.",
  },
  {
    id: "checkins-nav",
    dataTour: "nav-checkins",
    title: "Review check-ins",
    body: "Submitted check-ins show up here, waiting for your review.",
  },
  {
    id: "checkins-review",
    dataTour: "checkins-review-area",
    title: "Give feedback",
    body: "Open a check-in to write feedback text, add a Loom video link, and mark it as reviewed - your client gets notified by email.",
  },
];
```

- [ ] **Step 3: Update the welcome modal's preview list**

In `frontend/src/components/OnboardingModal.tsx`, find:

```tsx
              {isCoach ? (
                <>
                  <li>1. Adding your first client</li>
                  <li>2. Sharing the check-in link</li>
                  <li>3. Reviewing check-ins</li>
                </>
              ) : (
```

Replace with:

```tsx
              {isCoach ? (
                <>
                  <li>1. Adding your first client</li>
                  <li>2. Client settings & the magic link</li>
                  <li>3. Creating poses</li>
                  <li>4. Reviewing check-ins & giving feedback</li>
                </>
              ) : (
```

- [ ] **Step 4: Verify the frontend type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/contexts/OnboardingContext.tsx frontend/src/pages/Settings.tsx frontend/src/pages/ClientCheckins.tsx frontend/src/components/OnboardingModal.tsx
git commit -m "feat: extend coach onboarding tour to cover settings, magic link, poses, feedback"
```

---

### Task 4: Frontend — tour-end keep/delete modal

**Files:**
- Modify: `frontend/src/contexts/OnboardingContext.tsx`
- Create: `frontend/src/components/OnboardingEndModal.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: Add `tourClientId` state and the `"end"` phase to the context**

In `frontend/src/contexts/OnboardingContext.tsx`, update the `OnboardingContextValue` interface:

```tsx
interface OnboardingContextValue {
  phase: "modal" | "tour" | "end" | null;
  modalSlide: number;
  stepIndex: number;
  steps: TourStep[];
  tourClientId: number | null;
  start: () => void;
  nextModalSlide: () => void;
  startTour: () => void;
  nextStep: () => void;
  setTourClientId: (id: number) => void;
  finishTour: () => void;
  deleteTourClient: () => void;
  skip: () => void;
  restart: () => void;
}
```

Inside `OnboardingProvider`, add the new state (alongside the existing `useState` calls):

```tsx
  const [tourClientId, setTourClientIdState] = useState<number | null>(null);
```

Add `useMutation` and `api` are already imported at the top of the file — extend the import to include a client-delete call:

```tsx
import { api } from "../api/client";
```

(This import likely already exists — check before adding a duplicate line.)

Replace the existing `nextStep` function:

```tsx
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
```

with:

```tsx
  const nextStep = useCallback(() => {
    setStepIndex((i) => {
      const next = i + 1;
      if (next >= steps.length) {
        setPhase("end");
        return i;
      }
      return next;
    });
  }, [steps.length]);

  const setTourClientId = useCallback((id: number) => {
    setTourClientIdState(id);
  }, []);

  const finishTour = useCallback(() => {
    setPhase(null);
    setTourClientIdState(null);
    completeMutation.mutate();
  }, [completeMutation]);

  const deleteClientMutation = useMutation({
    mutationFn: (clientId: number) => api.clients.delete(clientId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clients"] });
      finishTour();
    },
  });

  const deleteTourClient = useCallback(() => {
    if (tourClientId !== null) {
      deleteClientMutation.mutate(tourClientId);
    } else {
      finishTour();
    }
  }, [tourClientId, deleteClientMutation, finishTour]);
```

Update the `value` object at the end of `OnboardingProvider` to include the new fields:

```tsx
  const value: OnboardingContextValue = {
    phase,
    modalSlide,
    stepIndex,
    steps,
    tourClientId,
    start,
    nextModalSlide,
    startTour,
    nextStep,
    setTourClientId,
    finishTour,
    deleteTourClient,
    skip,
    restart,
  };
```

- [ ] **Step 2: Add the `api.clients.delete` method**

In `frontend/src/api/client.ts`, find the `clients` object's `regenerateCheckinToken` method:

```typescript
    regenerateCheckinToken: (clientId: number) =>
      client.post<Client>(`/clients/${clientId}/checkin-token/regenerate`).then((r) => r.data),
```

Add right after it:

```typescript
    delete: (clientId: number) => client.delete(`/clients/${clientId}`),
```

- [ ] **Step 3: Create the end-of-tour modal component**

Write `frontend/src/components/OnboardingEndModal.tsx`:

```tsx
// frontend/src/components/OnboardingEndModal.tsx
import { useOnboarding } from "../contexts/OnboardingContext";

/** Letzter Schritt der Coach-Tour - siehe Design-Spec "Coach-Onboarding-
 * Tour v2" Teil 3. Bietet an, den während der Tour angelegten Test-
 * Klienten wieder zu löschen, damit der Coach sauber mit einem echten
 * ersten Klienten starten kann. */
export function OnboardingEndModal() {
  const { phase, tourClientId, finishTour, deleteTourClient } = useOnboarding();

  if (phase !== "end") return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-md rounded-xl border border-white/10 bg-surface p-6 shadow-2xl">
        <p className="text-2xl">🎉</p>
        <h1 className="mt-2 text-xl font-semibold text-white">You're all set!</h1>
        <p className="mt-2 text-sm text-slate-400">
          {tourClientId !== null
            ? "Want to keep the client you just created, or delete it to start clean with your first real client?"
            : "You've seen everything - happy coaching!"}
        </p>
        <div className="mt-5 flex flex-wrap gap-2">
          <button
            onClick={finishTour}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90"
          >
            {tourClientId !== null ? "Keep this client" : "Close"}
          </button>
          {tourClientId !== null && (
            <button
              onClick={deleteTourClient}
              className="rounded-lg border border-red-900/50 px-4 py-2 text-sm text-red-400 hover:bg-red-950/30"
            >
              Delete this client
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Mount the modal in `App.tsx`**

In `frontend/src/App.tsx`, import the component (alongside the existing `OnboardingModal`/`OnboardingTooltip` imports):

```tsx
import { OnboardingEndModal } from "./components/OnboardingEndModal";
```

Find `OnboardingModalGate`:

```tsx
function OnboardingModalGate() {
  const { phase } = useOnboarding();
  if (phase === "modal") return <OnboardingModal />;
  if (phase === "tour") return <OnboardingTooltip />;
  return null;
}
```

Replace with:

```tsx
function OnboardingModalGate() {
  const { phase } = useOnboarding();
  if (phase === "modal") return <OnboardingModal />;
  if (phase === "tour") return <OnboardingTooltip />;
  if (phase === "end") return <OnboardingEndModal />;
  return null;
}
```

- [ ] **Step 5: Note for the next task**

`Dashboard.tsx`'s current inline "Add Client" form (which still contains the old `phase`/`stepIndex`/`steps`/`nextStep`/tour-linking logic) is entirely replaced by a new `AddClientModal` component in Task 5 — that component will own the `setTourClientId` call directly. Nothing further to do here in `Dashboard.tsx` as part of Task 4; do not edit `Dashboard.tsx` in this task, Task 5 handles it.

- [ ] **Step 6: Verify the frontend type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/contexts/OnboardingContext.tsx frontend/src/api/client.ts frontend/src/components/OnboardingEndModal.tsx frontend/src/App.tsx
git commit -m "feat: add tour-end modal offering to keep or delete the tour's test client"
```

---

### Task 5: Frontend — Add-Client modal (replaces inline form)

**Files:**
- Create: `frontend/src/components/AddClientModal.tsx`
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: Create the modal component**

Write `frontend/src/components/AddClientModal.tsx`:

```tsx
// frontend/src/components/AddClientModal.tsx
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useOnboarding } from "../contexts/OnboardingContext";
import { useNavigate } from "react-router-dom";

/** Ersetzt das frühere Inline-Formular auf dem Dashboard - siehe
 * Design-Spec "Coach-Onboarding-Tour v2" Teil 5. Nur noch 3 Felder
 * (Name, Date of Birth, Gender) - Height und das ungenutzte Start Date
 * sind entfallen, Gewicht gibt es hier bewusst nicht (kommt erst mit
 * dem ersten Foto-Upload). */
export function AddClientModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [gender, setGender] = useState("");
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { phase, stepIndex, steps, nextStep, setTourClientId } = useOnboarding();

  const createMutation = useMutation({
    mutationFn: () =>
      api.clients.create({
        name,
        birth_date: birthDate.trim() === "" ? null : birthDate,
        gender: gender.trim() === "" ? null : gender,
      }),
    onSuccess: (createdClient) => {
      queryClient.invalidateQueries({ queryKey: ["clients"] });
      if (phase === "tour" && steps[stepIndex]?.id === "new-client") {
        setTourClientId(createdClient.id);
        nextStep();
        navigate(`/clients/${createdClient.id}/settings`);
        onClose();
      }
      // Außerhalb der Tour bleibt das Modal kurz mit einer Erfolgsmeldung
      // offen (siehe isSuccess-Zweig unten), statt sofort zu schließen.
    },
  });

  return (
    <div
      className="fixed inset-0 z-[90] flex items-center justify-center bg-black/70 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-sm rounded-xl border border-white/10 bg-surface p-6 shadow-2xl">
        <h2 className="mb-4 text-lg font-semibold text-white">Add New Client</h2>

        {createMutation.isSuccess ? (
          <div className="space-y-3">
            <p className="text-sm text-emerald-400">✓ Client added!</p>
            <button
              onClick={onClose}
              className="w-full rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90"
            >
              Close
            </button>
          </div>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (name.trim()) createMutation.mutate();
            }}
            className="space-y-3"
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
              <select
                value={gender}
                onChange={(e) => setGender(e.target.value)}
                className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
              >
                <option value="">Select…</option>
                <option value="Male">Male</option>
                <option value="Female">Female</option>
                <option value="Other">Other</option>
              </select>
            </label>

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={onClose}
                disabled={createMutation.isPending}
                className="rounded-lg border border-white/15 px-4 py-2 text-sm font-medium text-white hover:bg-white/5 disabled:opacity-40"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={!name.trim() || createMutation.isPending}
                className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-40"
              >
                {createMutation.isPending && (
                  <span className="h-3 w-3 animate-spin rounded-full border-2 border-slate-900 border-t-transparent" />
                )}
                {createMutation.isPending ? "Saving…" : "Save"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Remove the inline form from `Dashboard.tsx` and mount the modal instead**

In `frontend/src/pages/Dashboard.tsx`, remove the now-unused state and mutation: `name`, `heightCm`, `birthDate`, `gender`, `startDate` (via `useState`), and the entire `createMutation` block, since `AddClientModal` now owns its own form state and mutation. Also remove the `showForm`/`setShowForm` boolean state's *form-rendering* usage (keep the state itself, it now just controls modal visibility).

Replace:

```tsx
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
        setTourClientId(createdClient.id);
        nextStep();
        navigate(`/clients/${createdClient.id}/settings`);
      }
    },
  });
```

with:

```tsx
  const [showForm, setShowForm] = useState(false);

  const clientsQuery = useQuery({ queryKey: ["clients"], queryFn: api.clients.list });
  const summaryQuery = useQuery({
    queryKey: ["dashboard", "coach-summary"],
    queryFn: api.dashboard.coachSummary,
  });
```

The `createMutation`/tour-linking logic (previously inline in `Dashboard.tsx`, now owned entirely by `AddClientModal` from Step 1 above) needs to be removed from `Dashboard.tsx`'s `useOnboarding()` destructure too: find `const { phase, stepIndex, steps, nextStep } = useOnboarding();` near the top of `Dashboard()` and remove it entirely — check the rest of the file first to confirm nothing else in `Dashboard.tsx` still references `phase`/`stepIndex`/`steps`/`nextStep` (there shouldn't be, since the only usage was in the now-removed `createMutation`), and only remove the line if that's confirmed.

Find the form's `{showForm && ( ... )}` block (the entire multi-field `<form>...</form>` block) and replace it with:

```tsx
      {showForm && <AddClientModal onClose={() => setShowForm(false)} />}
```

Add the import at the top of `Dashboard.tsx`:

```tsx
import { AddClientModal } from "../components/AddClientModal";
```

- [ ] **Step 3: Verify the frontend type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors. Fix any leftover unused-variable or missing-import errors that surface from the removals in Step 2.

- [ ] **Step 4: Manual check in the browser**

Log in as a coach. Click "Add New Client" - modal should open centered, with Name/Date of Birth/Gender fields, Cancel and Save buttons. Verify: Cancel closes without creating anything; clicking outside the modal closes it too; Save with empty name is disabled; Save with a name shows a spinner then a green "Client added!" success message; the new client appears in the client list after closing.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/AddClientModal.tsx frontend/src/pages/Dashboard.tsx
git commit -m "feat: replace inline add-client form with a modal"
```

---

### Task 6: Frontend — "Delete client" danger zone on Settings

**Files:**
- Modify: `frontend/src/pages/Settings.tsx`
- Modify: `frontend/src/api/client.ts` (already done in Task 4, Step 2 — verify, don't re-add)

- [ ] **Step 1: Add the Danger Zone section**

In `frontend/src/pages/Settings.tsx`, read the full file first to see its existing imports (`useState`, `useMutation`, `useNavigate`, `Card`, etc.) and confirm `Card` supports the `danger` prop (it does, per `frontend/src/components/Card.tsx`). Add this new component at the end of the file:

```tsx
function DangerZoneSection({ clientId, clientName }: { clientId: number; clientName: string }) {
  const [showConfirm, setShowConfirm] = useState(false);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const deleteMutation = useMutation({
    mutationFn: () => api.clients.delete(clientId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clients"] });
      navigate("/dashboard");
    },
  });

  return (
    <Card title="Danger Zone" danger>
      {!showConfirm ? (
        <button
          onClick={() => setShowConfirm(true)}
          className="w-fit rounded-lg border border-red-900/50 px-4 py-2 text-sm text-red-400 hover:bg-red-950/30"
        >
          Delete client
        </button>
      ) : (
        <div className="space-y-2 rounded-lg border border-red-900/50 p-3">
          <p className="text-sm text-red-400">
            This will permanently delete {clientName} and ALL associated data (photos, poses,
            check-ins, weight history). This cannot be undone.
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => deleteMutation.mutate()}
              disabled={deleteMutation.isPending}
              className="rounded-lg bg-red-700 px-4 py-2 text-sm font-medium text-white hover:bg-red-600 disabled:opacity-50"
            >
              {deleteMutation.isPending ? "Deleting…" : "Delete permanently"}
            </button>
            <button
              onClick={() => setShowConfirm(false)}
              disabled={deleteMutation.isPending}
              className="rounded-lg border border-white/10 px-4 py-2 text-sm text-slate-300 hover:bg-black/30"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </Card>
  );
}
```

Ensure `useNavigate` (from `react-router-dom`) and `useQueryClient` are imported at the top of `Settings.tsx` — check the existing import lines first, add only what's missing.

- [ ] **Step 2: Render the section**

Find the end of the main `export default function Settings()`'s returned JSX (right before the final closing `</div>` that wraps the whole page — the same root div that has `data-tour` considerations from Task 3). Read the file to find its exact end, then add, right before that closing tag:

```tsx
      {clientQuery.data && (
        <DangerZoneSection clientId={clientIdNum} clientName={clientQuery.data.name} />
      )}
```

Adjust `clientQuery`/`clientIdNum` to match whatever the file's actual existing query/variable names are for the current client (read the file first — do not guess the exact identifiers).

- [ ] **Step 3: Verify the frontend type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Manual check in the browser**

Open a client's Settings page. Scroll to the bottom - a red "Danger Zone" card with "Delete client" should appear. Click it, confirm the warning text shows the client's name, click "Delete permanently", verify redirect to `/dashboard` and the client no longer appears in the list.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Settings.tsx
git commit -m "feat: add client deletion to the settings danger zone"
```

---

### Task 7: Final review and finish

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all tests pass except the pre-existing unrelated flaky `test_gemini_key_is_scoped_per_account`.

- [ ] **Step 2: Run the full frontend type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Manual end-to-end tour check in the browser**

As a coach account that hasn't completed onboarding (or via "Replay tour" on the Account page), run through the full tour: modal → Add Client (via the new modal) → client settings → magic link → add a pose → check-ins nav → check-ins review area → end-of-tour modal → delete the test client. Confirm every tooltip's target element is actually clickable throughout (the Task 2 bug fix), and that "Delete this client" actually removes it.

- [ ] **Step 4: Use superpowers:finishing-a-development-branch**

Follow that skill to present merge/PR/keep/discard options and complete the branch.
