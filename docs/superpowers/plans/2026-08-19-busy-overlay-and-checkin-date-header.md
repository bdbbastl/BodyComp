# Busy Overlay + Check-in Date Header Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the existing `BusyOverlay` during four slow data-processing actions (check-in delete, check-in submit, photo/day delete, AI judge analysis), and show the same day/week header the Timeline uses above photos on the magic-link check-in page and the coach's Check-ins tab.

**Architecture:** All four actions already use TanStack Query `useMutation` - each gets `show(label)` wired in right before `.mutate()` (or in an `onMutate` callback) and `hide()` in both `onSuccess` and `onError`, using the existing app-wide `useBusyOverlay()` hook. The date header reuses the existing `formatDateWithWeek`/`formatDateShortWithWeek` utilities, no new formatting logic.

**Tech Stack:** React, TanStack Query, existing `BusyOverlayContext`.

---

### Task 1: BusyOverlay for check-in delete and check-in submit

**Files:**
- Modify: `frontend/src/pages/ClientCheckins.tsx`
- Modify: `frontend/src/pages/CheckinSubmit.tsx`

- [ ] **Step 1: Wire the overlay into `ClientCheckins.tsx`'s delete mutation**

In `frontend/src/pages/ClientCheckins.tsx`, add the import (alongside the existing imports):

```tsx
import { useBusyOverlay } from "../contexts/BusyOverlayContext";
```

Inside the `ClientCheckins` component, add right after `const queryClient = useQueryClient();`:

```tsx
  const { show, hide } = useBusyOverlay();
```

Replace the `deleteMutation` definition:

```tsx
  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.checkins.delete(clientIdNum, id),
    onSuccess: () => {
      hide();
      setConfirmDeleteId(null);
      queryClient.invalidateQueries({ queryKey: ["checkins", clientIdNum] });
      // Falls die gelöschten Fotos bereits (weil reviewed) in
      // Timeline/Compare sichtbar waren, müssen die dortigen
      // Foto-Listen ebenfalls neu geladen werden.
      queryClient.invalidateQueries({ queryKey: ["photos", clientIdNum] });
    },
    onError: () => hide(),
  });
```

Replace the "Delete" confirm button's `onClick` (the one inside the `confirmDeleteId === checkin.id` branch, currently `onClick={() => deleteMutation.mutate(checkin.id)}`):

```tsx
                        <button
                          onClick={() => {
                            show("Deleting check-in…");
                            deleteMutation.mutate(checkin.id);
                          }}
                          disabled={deleteMutation.isPending}
                          className="rounded-lg bg-red-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-600 disabled:opacity-50"
                        >
                          {deleteMutation.isPending ? "Deleting…" : "Delete"}
                        </button>
```

- [ ] **Step 2: Wire the overlay into `CheckinSubmit.tsx`'s submit mutation**

In `frontend/src/pages/CheckinSubmit.tsx`, add the import (alongside the existing imports):

```tsx
import { useBusyOverlay } from "../contexts/BusyOverlayContext";
```

Inside the `CheckinSubmit` component, add right after `const queryClient = useQueryClient();`:

```tsx
  const { show, hide } = useBusyOverlay();
```

Replace the `submitMutation` definition:

```tsx
  const submitMutation = useMutation({
    mutationFn: () => {
      const parsed = parseWeightInput(weightKg);
      return api.publicCheckin.submit(token!, {
        weight_kg: parsed === null || Number.isNaN(parsed) ? null : parsed,
        client_note: note.trim() === "" ? undefined : note.trim(),
        files,
        poseIds: files.map((_, i) => photoPoses[i] as number),
      });
    },
    onSuccess: () => {
      hide();
      setWeightKg("");
      setNote("");
      setFiles([]);
      setPhotoPoses({});
      queryClient.invalidateQueries({ queryKey: ["public-checkin", token] });
    },
    onError: () => hide(),
  });
```

Replace the `<form onSubmit={...}>` handler (the one guarding on `submitMutation.isPending`/incomplete poses before calling `submitMutation.mutate()`):

```tsx
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (
              submitMutation.isPending ||
              (files.length > 0 && files.some((_, i) => !photoPoses[i]))
            ) {
              return;
            }
            show("Submitting check-in…");
            submitMutation.mutate();
          }}
          className="space-y-4 rounded-xl border border-white/5 bg-surface p-4"
        >
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Manual review**

Read through both modified files and confirm:
- `hide()` is called in both `onSuccess` and `onError` for both mutations (no path leaves the overlay stuck open).
- `show(...)` is only called right before `.mutate()`, not on every render.
- `CheckinSubmit.tsx` is reachable inside `BusyOverlayProvider` - confirm by reading `frontend/src/App.tsx` and checking that `<BusyOverlayProvider>` wraps the `<Routes>` element that includes the `/checkin/:token` route (it does, `BusyOverlayProvider` is the outermost wrapper in `App.tsx` per the current structure - re-verify this hasn't changed since the design spec was written).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ClientCheckins.tsx frontend/src/pages/CheckinSubmit.tsx
git commit -m "feat: show busy overlay while deleting/submitting a check-in"
```

---

### Task 2: BusyOverlay for Timeline photo/day delete

**Files:**
- Modify: `frontend/src/pages/Timeline.tsx`

- [ ] **Step 1: Read the current file to find both delete mutations and their trigger sites**

Read `frontend/src/pages/Timeline.tsx` in full first. There are two separate components with their own `useMutation` calls: the day-group component with `deleteDayMutation` (calls `api.photos.removeByDate`) and `PhotoCard` with `deleteMutation` (calls `api.photos.remove`). Both currently look like this (confirm exact current line numbers/surrounding code before editing, since other work may have touched this file since):

```tsx
  const deleteDayMutation = useMutation({
    mutationFn: () => api.photos.removeByDate(clientId, group.date),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["photos", clientId] });
      setConfirmingDelete(false);
    },
  });
```

and

```tsx
  const deleteMutation = useMutation({
    mutationFn: () => api.photos.remove(clientId, photo.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["photos", clientId] }),
  });
```

- [ ] **Step 2: Add the `useBusyOverlay` import and hook**

Add to the imports at the top of `frontend/src/pages/Timeline.tsx`:

```tsx
import { useBusyOverlay } from "../contexts/BusyOverlayContext";
```

In the day-group component (the one containing `deleteDayMutation`), add right after its existing `const queryClient = useQueryClient();`:

```tsx
  const { show, hide } = useBusyOverlay();
```

In `PhotoCard` (the one containing `deleteMutation`), add the same line right after its own `const queryClient = useQueryClient();`.

- [ ] **Step 3: Wire `show`/`hide` into `deleteDayMutation`**

Replace:

```tsx
  const deleteDayMutation = useMutation({
    mutationFn: () => api.photos.removeByDate(clientId, group.date),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["photos", clientId] });
      setConfirmingDelete(false);
    },
  });
```

with:

```tsx
  const deleteDayMutation = useMutation({
    mutationFn: () => api.photos.removeByDate(clientId, group.date),
    onSuccess: () => {
      hide();
      queryClient.invalidateQueries({ queryKey: ["photos", clientId] });
      setConfirmingDelete(false);
    },
    onError: () => hide(),
  });
```

Find the "Yes, delete" button that calls `deleteDayMutation.mutate()` and update its `onClick`:

```tsx
              <button
                onClick={() => {
                  show("Deleting day…");
                  deleteDayMutation.mutate();
                }}
                disabled={deleteDayMutation.isPending}
                className="rounded-full bg-red-500/80 px-2 py-1 font-medium text-white hover:bg-red-500 disabled:opacity-50"
              >
                Yes, delete
              </button>
```

- [ ] **Step 4: Wire `show`/`hide` into `PhotoCard`'s `deleteMutation`**

Replace:

```tsx
  const deleteMutation = useMutation({
    mutationFn: () => api.photos.remove(clientId, photo.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["photos", clientId] }),
  });
```

with:

```tsx
  const deleteMutation = useMutation({
    mutationFn: () => api.photos.remove(clientId, photo.id),
    onSuccess: () => {
      hide();
      queryClient.invalidateQueries({ queryKey: ["photos", clientId] });
    },
    onError: () => hide(),
  });
```

Find the button inside `PhotoCard` that triggers `deleteMutation.mutate()` (the "Delete photo?" confirm button) and add `show("Deleting photo…");` right before the `.mutate()` call in its `onClick`, following the same pattern as Step 3 above - read the exact current JSX first since the confirm UI's exact structure needs to be preserved, only the `onClick` body changes.

- [ ] **Step 5: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Manual review**

Confirm both mutations call `hide()` in both `onSuccess` and `onError`, and `show(...)` is called only at the actual delete-confirmation click site, not on every render or on the initial "Delete photo"/"Delete day" button (which only opens the confirm UI, doesn't delete anything yet).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Timeline.tsx
git commit -m "feat: show busy overlay while deleting a photo or a full day"
```

---

### Task 3: BusyOverlay for Compare AI judge analysis

**Files:**
- Modify: `frontend/src/pages/Compare.tsx`

- [ ] **Step 1: Add the import and hook**

Add to the imports at the top of `frontend/src/pages/Compare.tsx`:

```tsx
import { useBusyOverlay } from "../contexts/BusyOverlayContext";
```

Inside the `Compare` component, add near the other hook calls (e.g. right after `const [poseSelection, setPoseSelection] = useState<PoseSelection>("");` or any similarly-placed existing hook call - read the file to find a sensible spot near the top of the component body):

```tsx
  const { show, hide } = useBusyOverlay();
```

- [ ] **Step 2: Wire `hide()` into both AI mutations**

Replace:

```tsx
  const aiAnalysisMutation = useMutation({
    mutationFn: () =>
      api.comparisons.aiAnalysis(clientIdNum, {
        pose_id: Number(poseSelection),
        date_x: dateX,
        date_y: dateY,
      }),
  });
  const aiAnalysisAllMutation = useMutation({
    mutationFn: () => api.comparisons.aiAnalysisAll(clientIdNum, { date_x: dateX, date_y: dateY }),
  });
```

with:

```tsx
  const aiAnalysisMutation = useMutation({
    mutationFn: () =>
      api.comparisons.aiAnalysis(clientIdNum, {
        pose_id: Number(poseSelection),
        date_x: dateX,
        date_y: dateY,
      }),
    onSuccess: () => hide(),
    onError: () => hide(),
  });
  const aiAnalysisAllMutation = useMutation({
    mutationFn: () => api.comparisons.aiAnalysisAll(clientIdNum, { date_x: dateX, date_y: dateY }),
    onSuccess: () => hide(),
    onError: () => hide(),
  });
```

- [ ] **Step 3: Wire `show(...)` at the trigger site**

Find the button with `onClick={() => activeAiMutation.mutate()}` (the "🥊 AI analysis (judge rating)" button) and update it:

```tsx
            onClick={() => {
              show("Judge analyzing…");
              activeAiMutation.mutate();
            }}
```

Keep the surrounding `disabled={activeAiMutation.isPending}` and button label logic exactly as they are - only the `onClick` body changes.

- [ ] **Step 4: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Manual review**

Confirm the existing button-level "Judge analyzing…" label (shown via `activeAiMutation.isPending`) is untouched - the design spec explicitly states the overlay is additive, not a replacement for the existing inline pending state.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Compare.tsx
git commit -m "feat: show busy overlay while the AI judge is analyzing"
```

---

### Task 4: Day/week header on CheckinSubmit and ClientCheckins

**Files:**
- Modify: `frontend/src/pages/CheckinSubmit.tsx`
- Modify: `frontend/src/pages/ClientCheckins.tsx`

- [ ] **Step 1: Add the header to `CheckinSubmit.tsx`**

Add the import (alongside the existing imports):

```tsx
import { formatDateWithWeek } from "../utils/date";
```

Replace the client-name header block:

```tsx
        <div>
          <p className="text-xs text-slate-500">Check-in for</p>
          <h1 className="text-xl font-semibold text-white">{page.client_name}</h1>
        </div>
```

with:

```tsx
        <div>
          <p className="text-xs text-slate-500">Check-in for</p>
          <h1 className="text-xl font-semibold text-white">{page.client_name}</h1>
          <p className="mt-1 text-sm text-slate-400">
            {formatDateWithWeek(new Date().toISOString())}
          </p>
        </div>
```

- [ ] **Step 2: Add the header to `ClientCheckins.tsx`**

Add the import (alongside the existing imports):

```tsx
import { formatDateShortWithWeek } from "../utils/date";
```

Replace the photo-row block:

```tsx
                  {checkin.photos.length > 0 && (
                    <div className="flex gap-2 overflow-x-auto">
                      {checkin.photos.map((p) => (
                        <img
                          key={p.id}
                          src={mediaUrl(p.thumb_path)}
                          alt=""
                          className="h-20 w-20 shrink-0 rounded-lg object-cover"
                        />
                      ))}
                    </div>
                  )}
```

with:

```tsx
                  {checkin.photos.length > 0 && (
                    <div>
                      <p className="mb-1 text-xs text-slate-500">
                        {formatDateShortWithWeek(checkin.submitted_at)}
                      </p>
                      <div className="flex gap-2 overflow-x-auto">
                        {checkin.photos.map((p) => (
                          <img
                            key={p.id}
                            src={mediaUrl(p.thumb_path)}
                            alt=""
                            className="h-20 w-20 shrink-0 rounded-lg object-cover"
                          />
                        ))}
                      </div>
                    </div>
                  )}
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Manual review**

Confirm:
- `CheckinSubmit.tsx`'s date header shows the client device's current local date/week (via `new Date()`, no server round-trip), visible immediately on page load, not only after selecting files.
- `ClientCheckins.tsx`'s date header uses `checkin.submitted_at` (the actual submission timestamp), not the current date, and only renders when the check-in has at least one photo (same condition as the existing photo-row block).
- Formatting matches the Timeline's convention exactly (reusing `formatDateWithWeek`/`formatDateShortWithWeek`, no new date-formatting logic introduced).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/CheckinSubmit.tsx frontend/src/pages/ClientCheckins.tsx
git commit -m "feat: show day/week header above photos on check-in submit and coach check-ins view"
```

---

### Task 5: Holistic review + finish branch

- [ ] **Step 1: Run frontend type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 2: Manual review checklist**

- Confirm all four `BusyOverlay`-wired mutations (`ClientCheckins` delete, `CheckinSubmit` submit, `Timeline` photo delete, `Timeline` day delete, `Compare` AI judge x2) call `hide()` in BOTH `onSuccess` and `onError` - no lingering overlay after a failed request.
- Confirm no more than one `show(...)` call can be in flight at a time in normal usage (the app-wide overlay is a single shared state - two simultaneous slow actions would be unusual given the UI only allows one action at a time per page, but sanity-check there's no obvious way to trigger two overlapping `show()` calls from the same page).
- Confirm the date headers use the correct utility (`formatDateWithWeek` for `CheckinSubmit.tsx`'s full-width single header, `formatDateShortWithWeek` for `ClientCheckins.tsx`'s more compact per-card header) - matches the design spec's distinction.
- Confirm no backend changes were needed or made (this is a frontend-only plan) - `git diff --stat` against the base commit should show only files under `frontend/src/pages/`.

- [ ] **Step 3: Use the finishing-a-development-branch skill**

Invoke `superpowers:finishing-a-development-branch` to push per the user's standing "option 1" preference (this session works directly on `dev`).
