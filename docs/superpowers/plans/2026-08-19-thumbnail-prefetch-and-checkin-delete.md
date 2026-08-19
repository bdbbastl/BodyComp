# Thumbnail-Prefetch + Check-in-Löschen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parallelize thumbnail cold-start loading on the Timeline after a Railway redeploy, and let coaches permanently delete a check-in submission along with its photos.

**Architecture:** Backend `list_photos` prefetches missing thumbnail files from R2 in parallel (`ThreadPoolExecutor`, matching the existing pattern) before returning the photo list. A new `DELETE /clients/{client_id}/checkins/{checkin_id}` endpoint reuses the existing `_delete_photo_files` helper to remove a check-in's photos and files, then deletes the submission row. Frontend adds a Delete button with inline confirmation to the coach's Check-ins tab.

**Tech Stack:** FastAPI, SQLAlchemy, `concurrent.futures.ThreadPoolExecutor`, React, TanStack Query.

---

### Task 1: Parallel thumbnail prefetch in `list_photos`

**Files:**
- Modify: `backend/app/routers/photos.py`
- Test: `backend/tests/test_photos_router_scoped.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_photos_router_scoped.py`:

```python
def test_list_photos_prefetches_missing_thumbnails_in_parallel(client, db_session, monkeypatch):
    """Beweist tatsächliche Parallelität (nicht nur Code-Struktur): macht
    ensure_local() künstlich langsam und prüft, dass eine Liste mit 4
    fehlenden Thumbnails deutlich schneller durchläuft als 4x die
    künstliche Einzeldauer - bei sequenzieller Verarbeitung (z.B. weiter
    ein Download pro /media-Request statt Prefetch) wäre das unmöglich."""
    import time
    from app.models.photo import Photo, ProcessingStatus
    from app.models.pose import Pose
    from app.routers import photos as photos_router

    SLOW_ENSURE_LOCAL_SECONDS = 0.3

    calls = []

    def _slow_ensure_local(rel_path):
        calls.append(rel_path)
        time.sleep(SLOW_ENSURE_LOCAL_SECONDS)

    monkeypatch.setattr(photos_router, "ensure_local", _slow_ensure_local)

    client_id = _login_and_get_client(client, db_session)

    pose = Pose(client_id=client_id, name="Front", sort_order=0)
    db_session.add(pose)
    db_session.commit()

    for i in range(4):
        photo = Photo(
            client_id=client_id,
            filename=f"p{i}.jpg",
            original_path=f"photos_processed/{client_id}/p{i}.jpg",
            thumbnail_path=f"photos_processed/{client_id}/thumb_p{i}.jpg",
            taken_at=datetime(2026, 1, 1, 12 + i, 0, 0),
            status=ProcessingStatus.PROCESSED,
            pose_id=pose.id,
        )
        db_session.add(photo)
    db_session.commit()

    started = time.monotonic()
    response = client.get(f"/api/clients/{client_id}/photos")
    elapsed = time.monotonic() - started

    assert response.status_code == 200
    assert len(calls) == 4
    # Sequenziell wären das 4 * 0.3s = 1.2s - parallel deutlich darunter.
    assert elapsed < 4 * SLOW_ENSURE_LOCAL_SECONDS
```

Read `backend/tests/test_photos_router_scoped.py`'s existing `_login_and_get_client` helper and `datetime` import at the top of the file first to confirm they're already available (they are, per Task 2 of the earlier check-in-review-gated-timeline plan which added a similarly-structured concurrency test to this exact file) - reuse them as-is.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_photos_router_scoped.py -k prefetch -v`
Expected: FAIL (`ensure_local` isn't called at all from `list_photos` today, so `calls` stays empty and the length assertion fails).

- [ ] **Step 3: Add the prefetch helper and wire it into `list_photos`**

In `backend/app/routers/photos.py`, add this constant near the existing `PHOTO_PROCESSING_MAX_WORKERS` constant (same file, keep them close together):

```python
THUMBNAIL_PREFETCH_MAX_WORKERS = 8
```

Add this function right before `list_photos` (find it via `def list_photos(` in the file):

```python
def _prefetch_thumbnails(photos: list[Photo]) -> None:
    """Lädt fehlende Thumbnails parallel von R2 nach, BEVOR die Foto-Liste
    zurückgegeben wird - ensure_local() ist idempotent (No-Op wenn schon
    lokal vorhanden), hier betrifft es nur die tatsächlich fehlenden
    Dateien. Ohne dieses Prefetch würde jeder einzelne /media-Request sein
    eigenes R2-Download auslösen, was nach jedem Redeploy (ephemeres
    Railway-Dateisystem) zu langsam wirkendem, scheinbar seriellem
    Thumbnail-Laden auf der Timeline führt - siehe Design-Spec
    "Thumbnail-Prefetch + Check-in-Löschen".

    Nutzt denselben Pfad, den das Frontend tatsächlich für <img>-Tags
    anfragt (siehe PhotoOut.thumb_path in schemas/photo.py): thumbnail_path,
    mit Fallback auf preview_path oder original_path, falls noch kein
    Thumbnail generiert wurde."""
    thumb_paths = {
        p.thumbnail_path or p.preview_path or p.original_path for p in photos
    }
    missing = [
        rel_path
        for rel_path in thumb_paths
        if rel_path and not (settings.data_dir / rel_path).exists()
    ]
    if not missing:
        return
    with ThreadPoolExecutor(max_workers=THUMBNAIL_PREFETCH_MAX_WORKERS) as executor:
        list(executor.map(ensure_local, missing))
```

Replace the last line of `list_photos` (`return q.order_by(Photo.taken_at.desc()).all()`) with:

```python
    results = q.order_by(Photo.taken_at.desc()).all()
    _prefetch_thumbnails(results)
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_photos_router_scoped.py -k prefetch -v`
Expected: PASS.

- [ ] **Step 5: Run the full backend test suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all PASS except the pre-existing, unrelated `test_gemini_key_is_scoped_per_account` failure (known issue, not caused by this change).

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/photos.py backend/tests/test_photos_router_scoped.py
git commit -m "perf: prefetch missing thumbnails in parallel before returning photo list"
```

---

### Task 2: `DELETE /clients/{client_id}/checkins/{checkin_id}` endpoint

**Files:**
- Modify: `backend/app/routers/checkins.py`
- Test: `backend/tests/test_checkins_router.py`

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_checkins_router.py` already has a `_login(client, db_session, email="a@b.com", password="pw12345")` helper (returns the created `User`, logs the test client in) - client rows are created via `client.post("/api/clients", json={"name": "Max"}).json()` in existing tests in this file. Follow that exact pattern (no `_login_and_get_client` helper exists here, unlike `test_photos_router_scoped.py`).

Add to `backend/tests/test_checkins_router.py`:

```python
def test_delete_checkin_removes_submission_and_photos(client, db_session):
    from app.models.photo import Photo, ProcessingStatus
    from app.models.pose import Pose

    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    client_id = created["id"]

    pose = Pose(client_id=client_id, name="Front", sort_order=0)
    db_session.add(pose)
    db_session.commit()

    submission = CheckinSubmission(client_id=client_id, status=CheckinStatus.REVIEWED)
    db_session.add(submission)
    db_session.commit()
    db_session.refresh(submission)

    photo = Photo(
        client_id=client_id,
        filename="p1.jpg",
        original_path=f"photos_processed/{client_id}/p1_delete_test.jpg",
        taken_at=datetime(2026, 1, 1, 12, 0, 0),
        status=ProcessingStatus.PROCESSED,
        pose_id=pose.id,
        checkin_submission_id=submission.id,
    )
    db_session.add(photo)
    db_session.commit()
    photo_id = photo.id
    submission_id = submission.id

    response = client.delete(f"/api/clients/{client_id}/checkins/{submission_id}")
    assert response.status_code == 204

    assert db_session.query(CheckinSubmission).filter_by(id=submission_id).first() is None
    assert db_session.query(Photo).filter_by(id=photo_id).first() is None


def test_delete_checkin_leaves_day_log_untouched(client, db_session):
    from datetime import date as date_

    from app.models.day_log import DayLog

    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    client_id = created["id"]

    day_log = DayLog(client_id=client_id, date=date_(2026, 1, 1), weight_kg=80.0)
    db_session.add(day_log)
    submission = CheckinSubmission(
        client_id=client_id, status=CheckinStatus.REVIEWED, weight_kg=80.0
    )
    db_session.add(submission)
    db_session.commit()
    day_log_id = day_log.id
    submission_id = submission.id

    response = client.delete(f"/api/clients/{client_id}/checkins/{submission_id}")
    assert response.status_code == 204

    day_log_after = db_session.query(DayLog).filter_by(id=day_log_id).first()
    assert day_log_after is not None
    assert day_log_after.weight_kg == 80.0


def test_delete_checkin_404_for_unknown_id(client, db_session):
    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    response = client.delete(f"/api/clients/{created['id']}/checkins/999999")
    assert response.status_code == 404


def test_delete_checkin_404_for_foreign_client(client, db_session):
    _login(client, db_session, email="a@b.com")
    created = client.post("/api/clients", json={"name": "Max"}).json()
    submission = CheckinSubmission(client_id=created["id"], status=CheckinStatus.PENDING)
    db_session.add(submission)
    db_session.commit()
    submission_id = submission.id
    client.post("/api/auth/logout")

    _login(client, db_session, email="c@d.com")
    response = client.delete(f"/api/clients/{created['id']}/checkins/{submission_id}")
    assert response.status_code == 404
```

`datetime`, `CheckinStatus`, `CheckinSubmission` are already imported at the top of this file - no new top-level imports needed beyond what's already there.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_checkins_router.py -k delete_checkin -v`
Expected: FAIL (404 for all - no DELETE route exists yet on this router, so FastAPI returns 405 Method Not Allowed or 404 depending on route matching; either way not the expected 204/404-for-unknown-id behavior).

- [ ] **Step 3: Add `_delete_photo_files` export and the delete endpoint**

`_delete_photo_files` currently lives in `backend/app/routers/photos.py` as a module-level (non-underscore-prefixed-for-import-purposes, just conventionally private) function - it's directly importable. In `backend/app/routers/checkins.py`, update the imports:

```python
from app.models.checkin_submission import CheckinStatus, CheckinSubmission
from app.models.client import Client
from app.models.photo import Photo
from app.routers.clients import get_owned_client
from app.routers.photos import _delete_photo_files
from app.schemas.checkin import CheckinFeedbackUpdate, CheckinSubmissionOut
```

(This adds `Photo` and `from app.routers.photos import _delete_photo_files` to the existing import block - keep `CheckinStatus`, `CheckinSubmission`, `Client`, `get_owned_client`, `CheckinFeedbackUpdate`, `CheckinSubmissionOut` as they already are.)

Add this endpoint at the end of the file, after `update_checkin`:

```python
@router.delete("/{checkin_id}", status_code=204)
def delete_checkin(
    checkin_id: int, client_row: Client = Depends(get_owned_client), db: Session = Depends(get_db)
):
    """Löscht einen Check-in samt aller zugehörigen Fotos (Dateien + DB-
    Zeilen) unwiderruflich - siehe Design-Spec "Thumbnail-Prefetch +
    Check-in-Löschen". Der DayLog-Eintrag (Gewicht/Notizen) bleibt
    bestehen - Gewicht ist ein Tages-, kein Check-in-Attribut, konsistent
    mit delete_photo() in photos.py."""
    submission = (
        db.query(CheckinSubmission)
        .filter(CheckinSubmission.id == checkin_id, CheckinSubmission.client_id == client_row.id)
        .first()
    )
    if submission is None:
        raise HTTPException(404, "Check-in not found")

    photos = db.query(Photo).filter(Photo.checkin_submission_id == checkin_id).all()
    for photo in photos:
        _delete_photo_files(photo)
        db.delete(photo)
    db.delete(submission)
    db.commit()
```

IMPORTANT: before finalizing, run `cd backend && .venv/Scripts/python -c "import app.main"` to confirm this cross-router import (`checkins.py` importing from `photos.py`) doesn't create a circular import - `photos.py` does NOT import anything from `checkins.py` today (confirmed by reading its imports in Task 1), so this should be safe, but verify empirically since import order at module load time can still surprise you.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_checkins_router.py -v`
Expected: all PASS.

- [ ] **Step 5: Run the full backend test suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all PASS except the pre-existing `test_gemini_key_is_scoped_per_account` failure.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/checkins.py backend/tests/test_checkins_router.py
git commit -m "feat: let coaches delete a check-in submission and its photos"
```

---

### Task 3: Frontend API client - `checkins.delete`

**Files:**
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add the delete method**

In `frontend/src/api/client.ts`, inside the `checkins` namespace (right after the existing `update` method, which currently ends the object - read the file first to find the exact closing brace), add:

```typescript
    delete: (clientId: number, checkinId: number) =>
      client.delete(`/clients/${clientId}/checkins/${checkinId}`),
```

The full `checkins` namespace should read (for reference - apply just the addition, don't rewrite `list`/`update`):

```typescript
  checkins: {
    list: (clientId: number) =>
      client.get<CheckinSubmission[]>(`/clients/${clientId}/checkins`).then((r) => r.data),
    update: (
      clientId: number,
      checkinId: number,
      payload: { coach_feedback_text?: string; coach_feedback_video_url?: string; mark_reviewed?: boolean }
    ) =>
      client
        .patch<CheckinSubmission>(`/clients/${clientId}/checkins/${checkinId}`, payload)
        .then((r) => r.data),
    delete: (clientId: number, checkinId: number) =>
      client.delete(`/clients/${clientId}/checkins/${checkinId}`),
  },
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat: add checkins.delete to API client"
```

---

### Task 4: Delete button + inline confirmation in `ClientCheckins.tsx`

**Files:**
- Modify: `frontend/src/pages/ClientCheckins.tsx`

- [ ] **Step 1: Add delete state and mutation**

In `frontend/src/pages/ClientCheckins.tsx`, add a new state variable right after the existing `feedbackDrafts` state (inside the `ClientCheckins` component, after `const [feedbackDrafts, setFeedbackDrafts] = useState...`):

```tsx
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
```

Add a new mutation right after `updateMutation` (after its closing `});`):

```tsx
  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.checkins.delete(clientIdNum, id),
    onSuccess: () => {
      setConfirmDeleteId(null);
      queryClient.invalidateQueries({ queryKey: ["checkins", clientIdNum] });
      // Falls die gelöschten Fotos bereits (weil reviewed) in
      // Timeline/Compare sichtbar waren, müssen die dortigen
      // Foto-Listen ebenfalls neu geladen werden.
      queryClient.invalidateQueries({ queryKey: ["photos", clientIdNum] });
    },
  });
```

Before finalizing this step, read `frontend/src/pages/Timeline.tsx` and `frontend/src/pages/Compare.tsx` to confirm the exact `queryKey` used for their photo-list `useQuery` calls (this plan assumes `["photos", clientIdNum]` - adjust the invalidation key(s) above to match whatever key(s) those pages actually use, there may be more than one distinct key e.g. per pose-filter).

- [ ] **Step 2: Add the delete button + inline confirmation UI**

In the same file, inside the `isOpen &&` block, right after the closing `</div>` of the `flex gap-2` button row (the one containing "Save feedback" / "Mark as reviewed"), add a new block:

```tsx
                  {confirmDeleteId === checkin.id ? (
                    <div className="flex items-center gap-2 rounded-lg border border-red-900/50 bg-red-950/20 p-3">
                      <p className="flex-1 text-xs text-red-300">
                        Delete this check-in and its photos permanently?
                      </p>
                      <button
                        onClick={() => deleteMutation.mutate(checkin.id)}
                        disabled={deleteMutation.isPending}
                        className="rounded-lg bg-red-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-600 disabled:opacity-50"
                      >
                        {deleteMutation.isPending ? "Deleting…" : "Delete"}
                      </button>
                      <button
                        onClick={() => setConfirmDeleteId(null)}
                        className="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-slate-300 hover:bg-white/5"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setConfirmDeleteId(checkin.id)}
                      className="text-xs text-red-400 hover:underline"
                    >
                      Delete check-in
                    </button>
                  )}
```

This must be a sibling of the existing `<div className="flex gap-2">...</div>` button row, still inside the `{isOpen && (<div className="mt-4 space-y-3 border-t border-white/5 pt-4">...)}` wrapper, i.e. the last child before that wrapper's closing `</div>`.

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Manual review**

Read through the modified file and confirm:
- `confirmDeleteId` resets to `null` after a successful delete (via `onSuccess`).
- The confirm/cancel UI only shows for the specific check-in being deleted (`confirmDeleteId === checkin.id`), not all of them.
- Deleting a check-in that isn't currently expanded (`isOpen === false`) is impossible via this UI - that's fine, matches the existing pattern where all actions live inside the expanded card.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ClientCheckins.tsx
git commit -m "feat: add delete button with inline confirmation to check-ins tab"
```

---

### Task 5: Holistic review + finish branch

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all PASS except the pre-existing, unrelated `test_gemini_key_is_scoped_per_account` failure.

- [ ] **Step 2: Run frontend type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Manual review checklist**

- Confirm the thumbnail prefetch test genuinely proves parallelism (elapsed time well under N × per-file delay), not just that the code path was exercised.
- Confirm `_prefetch_thumbnails` only touches `thumbnail_path`/fallback paths, never `original_path`/`normalized_path` directly (no accidental full-res prefetch).
- Confirm `delete_checkin` is scoped by `get_owned_client` (a coach can never delete another coach's client's check-in) - read the dependency chain once more.
- Confirm deleting a check-in whose photos were already visible in Timeline/Compare (reviewed) actually removes them from the UI without a manual refresh (the query invalidation from Task 4, Step 1).
- Confirm no orphaned `Photo` rows remain in the DB pointing at a deleted `checkin_submission_id` (the endpoint deletes photos explicitly rather than relying on the `ON DELETE SET NULL` FK behavior, since the spec requires photos to be removed, not orphaned).

- [ ] **Step 4: Use the finishing-a-development-branch skill**

Invoke `superpowers:finishing-a-development-branch` to push per the user's standing "option 1" preference (this session works directly on `dev`).
