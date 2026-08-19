# Check-in Visibility + Compare Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the coach at-a-glance visibility into open check-ins (nav badge, dashboard widget counter + clickable rows), a per-photo origin indicator in the Timeline, and a smoother, less janky pose-switching experience in Compare.

**Architecture:** Mostly frontend-only, reusing data already loaded (`pending_checkins_count` on `ClientOut`) or requiring one small backend schema addition (`checkin_submission_id` on `PhotoOut`). Compare's smoothness fix uses TanStack Query's `placeholderData: keepPreviousData` plus background prefetching of neighboring poses' data and images.

**Tech Stack:** FastAPI/Pydantic, React, TanStack Query v5.

---

### Task 1: Expose `checkin_submission_id` on `PhotoOut`

**Files:**
- Modify: `backend/app/schemas/photo.py`
- Test: `backend/tests/test_photos_router_scoped.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_photos_router_scoped.py`:

```python
def test_list_photos_includes_checkin_submission_id(client, db_session):
    from app.models.checkin_submission import CheckinStatus, CheckinSubmission
    from app.models.photo import Photo, ProcessingStatus
    from app.models.pose import Pose

    client_id = _login_and_get_client(client, db_session)

    pose = Pose(client_id=client_id, name="Front", sort_order=0)
    db_session.add(pose)
    db_session.commit()

    submission = CheckinSubmission(client_id=client_id, status=CheckinStatus.REVIEWED)
    db_session.add(submission)
    db_session.commit()
    db_session.refresh(submission)

    checkin_photo = Photo(
        client_id=client_id,
        filename="from_checkin.jpg",
        original_path=f"photos_processed/{client_id}/from_checkin.jpg",
        taken_at=datetime(2026, 1, 1, 12, 0, 0),
        status=ProcessingStatus.PROCESSED,
        pose_id=pose.id,
        checkin_submission_id=submission.id,
    )
    coach_photo = Photo(
        client_id=client_id,
        filename="from_coach.jpg",
        original_path=f"photos_processed/{client_id}/from_coach.jpg",
        taken_at=datetime(2026, 1, 2, 12, 0, 0),
        status=ProcessingStatus.PROCESSED,
        pose_id=pose.id,
        checkin_submission_id=None,
    )
    db_session.add_all([checkin_photo, coach_photo])
    db_session.commit()

    response = client.get(f"/api/clients/{client_id}/photos")
    assert response.status_code == 200
    by_filename = {p["filename"]: p for p in response.json()}

    assert by_filename["from_checkin.jpg"]["checkin_submission_id"] == submission.id
    assert by_filename["from_coach.jpg"]["checkin_submission_id"] is None
```

Check whether `datetime` is already imported at the top of this test file (it is, per earlier tasks in this file) - no new import needed.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_photos_router_scoped.py -k checkin_submission_id -v`
Expected: FAIL (`KeyError: 'checkin_submission_id'` - the field isn't in the response yet).

- [ ] **Step 3: Add the field**

In `backend/app/schemas/photo.py`, add `checkin_submission_id: int | None` to `PhotoOut` (after `day_log_id: int | None`):

```python
class PhotoOut(BaseModel):
    id: int
    filename: str
    original_path: str
    preview_path: str | None
    normalized_path: str | None
    thumbnail_path: str | None
    taken_at: datetime
    status: ProcessingStatus
    pose_id: int | None
    day_log_id: int | None
    checkin_submission_id: int | None
    width: int | None
    height: int | None

    class Config:
        from_attributes = True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_photos_router_scoped.py -k checkin_submission_id -v`
Expected: PASS.

- [ ] **Step 5: Run the full backend test suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all PASS except the two pre-existing, unrelated flaky/known failures (`test_gemini_key_is_scoped_per_account`, and occasionally `test_assign_bulk_processes_multiple_photos_concurrently` under load - re-run the latter in isolation if it fails, it passes standalone).

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/photo.py backend/tests/test_photos_router_scoped.py
git commit -m "feat: expose checkin_submission_id on PhotoOut for Timeline origin indicator"
```

---

### Task 2: Widen `Card`'s `title` prop to accept `ReactNode`

**Files:**
- Modify: `frontend/src/components/Card.tsx`

- [ ] **Step 1: Update the type and JSX**

Replace `frontend/src/components/Card.tsx` in full:

```tsx
// frontend/src/components/Card.tsx
import type { ReactNode } from "react";

interface CardProps {
  title?: ReactNode;
  description?: string;
  children: ReactNode;
  className?: string;
  danger?: boolean; // roter Rahmen statt Standard - für die Danger Zone
}

/** Einheitlicher Abschnitts-Container mit optionaler Überschrift/
 * Beschreibung - siehe Design-Spec "UX-Politur" Abschnitt 2. Ersetzt die
 * bisher pro Sektion wiederholten `rounded-xl border ... bg-surface p-4`
 * + manuelle <h2>-Blöcke in Account.tsx. `title` akzeptiert seit dem
 * Check-in-Sichtbarkeits-Paket auch JSX (z.B. Titel + Zähler-Badge),
 * nicht mehr nur reinen Text. */
export function Card({ title, description, children, className = "", danger = false }: CardProps) {
  return (
    <div
      className={`rounded-xl border p-4 ${
        danger ? "border-red-900/40 bg-surface" : "border-white/5 bg-surface"
      } ${className}`}
    >
      {title && <h2 className="mb-1 text-lg font-semibold text-white">{title}</h2>}
      {description && <p className="mb-4 text-sm text-slate-400">{description}</p>}
      {children}
    </div>
  );
}
```

Only `title?: string` changed to `title?: ReactNode`, plus the updated doc comment - everything else is unchanged.

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors (every existing `title="..."` call site still type-checks fine, since a string is a valid `ReactNode`).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Card.tsx
git commit -m "feat: widen Card title prop to accept ReactNode"
```

---

### Task 3: Nav badge for open check-ins (`ClientShell.tsx`)

**Files:**
- Modify: `frontend/src/components/ClientShell.tsx`

- [ ] **Step 1: Add the badge inside `renderNavItem`**

In `frontend/src/components/ClientShell.tsx`, find the `renderNavItem` function. Its `<NavLink>` currently ends with:

```tsx
          <Icon size={17} aria-hidden="true" />
          {!options.collapsed && item.label}
        </NavLink>
      </div>
    );
  };
```

Replace it with:

```tsx
          <Icon size={17} aria-hidden="true" />
          {!options.collapsed && item.label}
          {item.to === "checkins" && (clientQuery.data?.pending_checkins_count ?? 0) > 0 && (
            <span className="ml-auto flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold text-white">
              {clientQuery.data!.pending_checkins_count}
            </span>
          )}
        </NavLink>
      </div>
    );
  };
```

`clientQuery` is already defined earlier in the same component (`const clientQuery = useQuery({ queryKey: ["clients", Number(clientId)], ... })`) and is in scope inside `renderNavItem`, since `renderNavItem` is a closure defined inside the `ClientShell` function body - no new prop/parameter needed.

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Manual review**

Confirm: the badge only renders for the "Check-ins" nav item, only when `pending_checkins_count > 0`, and appears both in the expanded (with label) and collapsed (icon-only) sidebar states, since the JSX line isn't gated on `options.collapsed`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ClientShell.tsx
git commit -m "feat: show open check-ins count badge on Check-ins nav item"
```

---

### Task 4: Dashboard "Unseen check-ins" widget - counter + clickable rows

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: Replace `PendingCheckinsWidget`**

In `frontend/src/pages/Dashboard.tsx`, replace the entire `PendingCheckinsWidget` function:

```tsx
function PendingCheckinsWidget({
  items,
  isLoading,
}: {
  items: PendingCheckinSummary[];
  isLoading: boolean;
}) {
  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          Unseen check-ins
          {items.length > 0 && (
            <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1 text-xs font-semibold text-white">
              {items.length}
            </span>
          )}
        </span>
      }
    >
      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {!isLoading && items.length === 0 && (
        <p className="text-sm text-slate-500">No pending check-ins.</p>
      )}
      <div className="max-h-64 space-y-2 overflow-y-auto">
        {items.map((item) => (
          <Link
            key={item.id}
            to={`/clients/${item.client_id}/checkins`}
            className="flex items-center justify-between gap-2 rounded-lg bg-amber-500/5 px-3 py-2 hover:bg-amber-500/10"
          >
            <div className="min-w-0">
              <p className="truncate text-sm text-slate-200">{item.client_name}</p>
              <p className="text-xs text-slate-500">
                {new Date(item.submitted_at).toLocaleDateString("en-US")}
                {item.weight_kg != null ? ` · ${item.weight_kg} kg` : ""}
              </p>
            </div>
          </Link>
        ))}
      </div>
    </Card>
  );
}
```

This removes `markSeenMutation` entirely (it's no longer referenced anywhere), and the row is now a `<Link>` instead of a `<div>` + separate "Mark seen" `<button>`.

- [ ] **Step 2: Remove the now-unused `useQueryClient` import if nothing else in the file needs it**

Check `frontend/src/pages/Dashboard.tsx`'s top-level imports - `useQueryClient` is still used elsewhere in the file (the top-level `Dashboard` component uses `queryClient.invalidateQueries` in `createMutation.onSuccess`), so the import stays. Just confirm by reading the file - do not remove the import.

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors. If `useMutation` becomes unused as an import ANYWHERE in the file, check - it's still used by `createMutation` at the top of `Dashboard`, so the import stays too.

- [ ] **Step 4: Manual review**

Confirm: no "Mark seen" button remains anywhere in the file, each row navigates to `/clients/{client_id}/checkins` on click, and the row has a visible hover state (`hover:bg-amber-500/10`) consistent with `ClientsWidget`'s and `NeedsAttentionWidget`'s row hover treatment.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat: add counter badge and clickable rows to Unseen check-ins widget"
```

---

### Task 5: Timeline photo origin indicator (Coach upload vs. client check-in)

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/pages/Timeline.tsx`

- [ ] **Step 1: Add the field to the `Photo` type**

In `frontend/src/types/index.ts`, find the `Photo` interface and add `checkin_submission_id: number | null;` after `day_log_id` (or wherever the interface currently lists `taken_at`/similar fields - read the file first to find the exact right spot matching the backend's field ordering, doesn't need to match exactly but should sit near the other per-photo metadata fields).

- [ ] **Step 2: Run type-check to confirm the field is now available**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors (adding an optional-style field to an interface doesn't break existing object literals unless something constructs a `Photo` object manually without it - check for that; if any test/mock construction of a `Photo` object exists in `frontend/src`, it would now fail to type-check and need `checkin_submission_id: null` added - there are no such standalone constructions in this codebase's frontend source today since `Photo` objects only ever come from API responses, but verify via the tsc run).

- [ ] **Step 3: Add the badge to `PhotoCard`**

In `frontend/src/pages/Timeline.tsx`, find `PhotoCard`'s `<img>` element (inside the `<div className="relative">` wrapper). Insert the badge as the first child of that `relative` div, right before the `<img>`:

```tsx
      <div className="relative">
        <span
          title={photo.checkin_submission_id != null ? "From client check-in" : "Uploaded by coach"}
          className="absolute left-1 top-1 z-10 flex h-6 w-6 items-center justify-center rounded-full bg-black/60 text-xs backdrop-blur"
        >
          {photo.checkin_submission_id != null ? "📨" : "📤"}
        </span>
        <img
          src={mediaUrl(photo.thumb_path)}
          alt={photo.pose_id ? poseNameById.get(photo.pose_id) ?? "Photo" : "Photo"}
          className="aspect-[3/4] w-full cursor-zoom-in object-cover"
          loading="lazy"
          onClick={() => !confirmingDelete && onOpen(photo)}
        />
```

Positioned `left-1 top-1` (mirroring the existing delete button's `right-1 top-1`, so they sit symmetrically without colliding), `z-10` so it stays above the image but the existing `confirmingDelete` overlay (`absolute inset-0 ... bg-black/80`) still covers it when the delete-confirm state is active (that overlay has no explicit z-index, but since it's a later sibling in the DOM it stacks on top in normal flow - verify this visually, add `z-20` to the confirm overlay if the badge shows through it unexpectedly).

- [ ] **Step 4: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Manual review**

Confirm the badge shows 📨 for photos with a non-null `checkin_submission_id` and 📤 otherwise, doesn't overlap the delete button (opposite corners), and the `confirmingDelete` state's dark overlay still visually covers it (no double-badge-and-delete-UI showing simultaneously in a confusing way).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/pages/Timeline.tsx
git commit -m "feat: show photo origin indicator (coach upload vs client check-in) in Timeline"
```

---

### Task 6: Compare - hide pose switcher until both dates chosen, smoother pose-switching

**Files:**
- Modify: `frontend/src/pages/Compare.tsx`

- [ ] **Step 1: Hide the pose switcher until both dates are selected**

In `frontend/src/pages/Compare.tsx`, find:

```tsx
      {poses.length > 0 && (
        <PoseNavBar poses={poses} currentPoseId={poseSelection} onNavigate={goToPose} disabled={isAllPoses} />
      )}
```

Replace with:

```tsx
      {poses.length > 0 && dateX !== "" && dateY !== "" && (
        <PoseNavBar poses={poses} currentPoseId={poseSelection} onNavigate={goToPose} disabled={isAllPoses} />
      )}
```

- [ ] **Step 2: Add `keepPreviousData` to `comparisonQuery`**

Update the import line at the top of the file:

```tsx
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
```

(Adds `keepPreviousData` and `useQueryClient` to the existing `useMutation, useQuery` import - `useQueryClient` is needed for Step 3's prefetching.)

Find `comparisonQuery`:

```tsx
  const comparisonQuery = useQuery({
    queryKey: ["comparison", clientIdNum, poseSelection, dateX, dateY],
    queryFn: () =>
      api.comparisons.get(clientIdNum, { pose_id: Number(poseSelection), date_x: dateX, date_y: dateY }),
    enabled: typeof poseSelection === "number" && dateX !== "" && dateY !== "",
    retry: false,
  });
```

Add `placeholderData: keepPreviousData`:

```tsx
  const comparisonQuery = useQuery({
    queryKey: ["comparison", clientIdNum, poseSelection, dateX, dateY],
    queryFn: () =>
      api.comparisons.get(clientIdNum, { pose_id: Number(poseSelection), date_x: dateX, date_y: dateY }),
    enabled: typeof poseSelection === "number" && dateX !== "" && dateY !== "",
    placeholderData: keepPreviousData,
    retry: false,
  });
```

- [ ] **Step 3: Add neighbor-pose prefetching**

Add `const queryClient = useQueryClient();` right after the existing `const { show, hide } = useBusyOverlay();` line near the top of the `Compare` component.

Add a new `useEffect` right after the existing `goToPose`/keyboard-navigation `useEffect` block (after its closing `}, [poseSelection, poses]);`):

```tsx
  // Nachbar-Posen im Hintergrund vorladen (Vergleichsdaten + Bilddateien),
  // damit ein Klick auf ‹/› meist schon auf warme Daten trifft, statt
  // jedes Mal neu zu laden - siehe Live-Feedback "ruckelfreies Wechseln".
  // Nur bei einer einzelnen gewählten Pose (nicht "Alle Posen", wo es
  // keine Nachbar-Navigation gibt) und nur wenn beide Termine gewählt sind.
  useEffect(() => {
    if (typeof poseSelection !== "number" || dateX === "" || dateY === "" || poses.length < 2) {
      return;
    }
    const currentIndex = poses.findIndex((p) => p.id === poseSelection);
    if (currentIndex === -1) return;
    const prevPose = poses[(currentIndex - 1 + poses.length) % poses.length];
    const nextPose = poses[(currentIndex + 1) % poses.length];

    [prevPose, nextPose].forEach((neighborPose) => {
      queryClient
        .prefetchQuery({
          queryKey: ["comparison", clientIdNum, neighborPose.id, dateX, dateY],
          queryFn: () =>
            api.comparisons.get(clientIdNum, {
              pose_id: neighborPose.id,
              date_x: dateX,
              date_y: dateY,
            }),
        })
        .then(() => {
          const cached = queryClient.getQueryData<{
            photo_x: Photo;
            photo_y: Photo;
          }>(["comparison", clientIdNum, neighborPose.id, dateX, dateY]);
          if (!cached) return;
          // Bild-Bytes selbst vorwärmen (Browser-HTTP-Cache + serverseitiger
          // ensure_local()-Cache über den normalen /media-Request) - die
          // Vergleichsdaten allein enthalten nur Pfade, keine Bilddaten.
          [cached.photo_x, cached.photo_y].forEach((photo) => {
            const src = mediaUrl(
              normalize && photo.normalized_path ? photo.normalized_path : photo.display_path
            );
            new Image().src = src;
          });
        })
        .catch(() => {
          // Best effort - ein fehlgeschlagenes Prefetch (z.B. Nachbar-Pose
          // hat für dieses Datumspaar kein Foto) soll nichts sichtbar
          // beeinträchtigen, das eigentliche Umschalten zeigt den Fehler
          // ggf. ganz normal über comparisonQuery.isError an.
        });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [poseSelection, dateX, dateY, poses, clientIdNum, normalize]);
```

- [ ] **Step 4: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Manual review**

Confirm:
- `PoseNavBar` genuinely stays hidden until both `dateX` and `dateY` are non-empty.
- The prefetch `useEffect` doesn't fire when `poseSelection` is `"all"` or `""` (guarded by `typeof poseSelection !== "number"`).
- `resolveSrc`'s existing logic (`normalize && photo.normalized_path ? photo.normalized_path : photo.display_path`) is mirrored correctly in the new prefetch code's image-URL construction, so warmed images actually match what gets displayed after switching.
- No infinite prefetch loop - the effect only prefetches the two immediate neighbors on each pose/date change, doesn't recursively prefetch further out.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Compare.tsx
git commit -m "feat: hide pose switcher until dates chosen, prefetch neighbor poses for smoother switching"
```

---

### Task 7: Holistic review + finish branch

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all PASS except the two pre-existing, unrelated known-flaky failures.

- [ ] **Step 2: Run frontend type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Manual review checklist**

- Confirm every requirement from the design spec has a corresponding task: nav badge (Task 3), dashboard widget counter + clickable rows + removed "Mark seen" (Task 4), Timeline origin indicator (Task 5), Compare pose-switcher visibility (Task 6 Step 1), Compare smoother switching via `keepPreviousData` + prefetch (Task 6 Steps 2-3).
- Confirm `markSeenMutation` and the old `api.checkins.update(..., { mark_reviewed: true })` call site inside `PendingCheckinsWidget` are both fully gone (not just unused) - the "Mark as reviewed" flow still exists and works fine on the Check-ins page itself (`ClientCheckins.tsx`), which is untouched by this plan.
- Confirm `Card`'s `title` widening didn't silently change any existing Card's rendered output (spot-check `git diff` shows only the type change + the two intentional new JSX-title usages).
- Confirm no backend changes beyond the one additive schema field (Task 1) - `git diff --stat` against the base commit should show exactly one file under `backend/app/schemas/` plus its test.

- [ ] **Step 4: Use the finishing-a-development-branch skill**

Invoke `superpowers:finishing-a-development-branch` to push per the user's standing "option 1" preference (this session works directly on `dev`).
