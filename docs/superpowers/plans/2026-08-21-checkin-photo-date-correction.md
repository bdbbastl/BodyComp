# Check-in Photo Date Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a client correct the ermittelte (EXIF/mtime-derived) photo date on the magic-link check-in page by clicking it and picking a new date, which overrides `taken_at` for every photo in that submission.

**Architecture:** Backend gains an optional `photo_date` form field on `POST /api/public/checkin/{token}/submit`, validated (parseable ISO date, not in the future) and, when present, applied to `Photo.taken_at` for every photo in the submission right after the existing EXIF-based sync — so DayLog grouping (which reads `taken_at`) picks it up automatically with no separate code path. Frontend turns the existing read-only date label into a click-to-edit control backed by a native `<input type="date">`, only when all selected photos already share one EXIF date.

**Tech Stack:** FastAPI/SQLAlchemy backend (Python, pytest, `piexif`/Pillow for test fixtures), React/TypeScript frontend (Vite, `node --test` for pure-function tests, `tsc --noEmit` for type-checking), lucide-react icons.

Spec: [docs/superpowers/specs/2026-08-21-checkin-photo-date-correction-design.md](../specs/2026-08-21-checkin-photo-date-correction-design.md)

---

## Task 1: Backend — validate the `photo_date` form field

**Files:**
- Modify: `backend/app/routers/public_checkin.py`
- Test: `backend/tests/test_public_checkin_router.py`

- [ ] **Step 1: Write the failing tests**

Add these three tests to `backend/tests/test_public_checkin_router.py`, right after `test_submit_checkin_with_valid_pose_processes_photo_immediately` (before `test_submit_checkin_blocked_for_single_account_after_free_quota`):

```python
def test_submit_checkin_rejects_invalid_photo_date_format(client, db_session):
    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    token = created["checkin_token"]

    response = client.post(
        f"/api/public/checkin/{token}/submit",
        data={"weight_kg": "80", "photo_date": "not-a-date"},
    )
    assert response.status_code == 400


def test_submit_checkin_rejects_future_photo_date(client, db_session):
    from datetime import date, timedelta

    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    token = created["checkin_token"]

    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    response = client.post(
        f"/api/public/checkin/{token}/submit",
        data={"weight_kg": "80", "photo_date": tomorrow},
    )
    assert response.status_code == 400


def test_submit_checkin_accepts_todays_photo_date(client, db_session):
    from datetime import date

    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    token = created["checkin_token"]

    response = client.post(
        f"/api/public/checkin/{token}/submit",
        data={"weight_kg": "80", "photo_date": date.today().isoformat()},
    )
    assert response.status_code == 201
```

- [ ] **Step 2: Run tests to verify the two rejection tests fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_public_checkin_router.py -k "photo_date" -v`
Expected: `test_submit_checkin_rejects_invalid_photo_date_format` and `test_submit_checkin_rejects_future_photo_date` FAIL (got 201, expected 400) — the `photo_date` field is currently silently ignored by FastAPI since no such parameter is declared. `test_submit_checkin_accepts_todays_photo_date` already PASSES (nothing rejects it yet) — that's expected, it's a regression guard for the next step, not a RED test.

- [ ] **Step 3: Add the `photo_date` parameter and validation**

In `backend/app/routers/public_checkin.py`, add `photo_date` to the `submit_checkin` signature:

```python
def submit_checkin(
    weight_kg: str | None = Form(default=None),
    client_note: str | None = Form(default=None),
    photo_date: str | None = Form(default=None),
    files: list[UploadFile] = File(default=[]),
    pose_ids: list[int] = Form(default=[]),
    client_row: Client = Depends(get_client_by_checkin_token),
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(checkin_submit_rate_limit),
):
```

Then, right after the existing weight-parsing block:

```python
    try:
        parsed_weight_kg = parse_weight_kg(weight_kg)
    except ValueError:
        raise HTTPException(400, "Weight must be a number (comma or dot as decimal separator)")
```

add the new validation block (before `submission = CheckinSubmission(...)`):

```python
    # Manuelle Datums-Korrektur des Klienten (siehe Design-Spec
    # "Check-in: Foto-Datum manuell korrigieren") - überschreibt bei
    # Erfolg unten das per EXIF/mtime ermittelte taken_at aller Fotos
    # dieser Einreichung. Keine Zukunftsdaten (Server-seitig durchgesetzt,
    # das Frontend begrenzt den Picker zusätzlich per `max`).
    parsed_photo_date: date_ | None = None
    if photo_date is not None:
        try:
            parsed_photo_date = date_.fromisoformat(photo_date)
        except ValueError:
            raise HTTPException(400, "Invalid date format")
        if parsed_photo_date > date_.today():
            raise HTTPException(400, "Date cannot be in the future")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_public_checkin_router.py -k "photo_date" -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Run the full public-checkin test file to check for regressions**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_public_checkin_router.py -v`
Expected: all tests PASS (17 previous + 3 new = 20).

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/public_checkin.py backend/tests/test_public_checkin_router.py
git commit -m "feat: validate optional photo_date field on check-in submit"
```

---

## Task 2: Backend — apply the `photo_date` override to `taken_at`

**Files:**
- Modify: `backend/app/routers/public_checkin.py`
- Test: `backend/tests/test_public_checkin_router.py`

- [ ] **Step 1: Write the failing test**

Add this test to `backend/tests/test_public_checkin_router.py`, right after `test_submit_checkin_uses_photo_exif_date_not_upload_date` (it reuses the `_jpeg_with_exif_date_taken` helper already defined above that test):

```python
def test_submit_checkin_photo_date_override_replaces_exif_date(client, db_session):
    """Regression: wenn der Klient das ermittelte Datum korrigiert
    (`photo_date`), muss das für ALLE Fotos der Einreichung gelten -
    sowohl `Photo.taken_at` selbst (Timeline/Compare zeigen sonst das
    falsche Datum) als auch die DayLog-Zuordnung. Das ursprüngliche
    EXIF-Datum darf danach nirgends mehr als DayLog auftauchen."""
    from datetime import date, datetime

    from app.models.day_log import DayLog
    from app.models.photo import Photo
    from app.models.pose import Pose

    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    token = created["checkin_token"]
    pose = Pose(client_id=created["id"], name="Front Relaxed", sort_order=0)
    db_session.add(pose)
    db_session.commit()
    db_session.refresh(pose)

    exif_date = datetime(2026, 1, 5, 8, 30, 0)
    override_date = date(2026, 1, 3)
    assert override_date != exif_date.date()  # Testannahme: eindeutig unterschiedliche Daten
    jpeg_bytes = _jpeg_with_exif_date_taken(exif_date)

    response = client.post(
        f"/api/public/checkin/{token}/submit",
        data={
            "weight_kg": "80",
            "pose_ids": str(pose.id),
            "photo_date": override_date.isoformat(),
        },
        files={"files": ("p1.jpg", jpeg_bytes, "image/jpeg")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["photos"][0]["taken_at"].startswith("2026-01-03")

    photo = db_session.query(Photo).filter(Photo.checkin_submission_id == body["id"]).first()
    assert photo.taken_at == datetime(2026, 1, 3, 0, 0, 0)

    photo_day_log = (
        db_session.query(DayLog)
        .filter(DayLog.client_id == created["id"], DayLog.date == override_date)
        .first()
    )
    assert photo_day_log is not None

    exif_day_log = (
        db_session.query(DayLog)
        .filter(DayLog.client_id == created["id"], DayLog.date == exif_date.date())
        .first()
    )
    assert exif_day_log is None, "photo must NOT stay grouped under its original EXIF date"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_public_checkin_router.py -k photo_date_override_replaces -v`
Expected: FAIL — `photo.taken_at` is still `2026-01-05 08:30:00` (the EXIF date), assertion `photo.taken_at == datetime(2026, 1, 3, 0, 0, 0)` fails, because nothing applies the override yet.

- [ ] **Step 3: Implement the override**

In `backend/app/routers/public_checkin.py`, change the import line from:

```python
from datetime import date as date_
```

to:

```python
from datetime import date as date_, datetime, time
```

Then find this existing block (inside the `if files:` section, right after photos are written and synced):

```python
        for photo, _pose_id in photos_to_process:
            photo.checkin_submission_id = submission.id
        db.commit()
```

Replace it with:

```python
        for photo, _pose_id in photos_to_process:
            photo.checkin_submission_id = submission.id
        if parsed_photo_date is not None:
            # Klient hat das ermittelte Datum korrigiert - gilt für ALLE
            # Fotos dieser Einreichung, überschreibt taken_at direkt, damit
            # DayLog-Zuordnung (liest taken_at gleich unten), Timeline und
            # Compare konsistent bleiben. Keine echte Aufnahme-Uhrzeit
            # bekannt -> Mitternacht als Konvention.
            override_taken_at = datetime.combine(parsed_photo_date, time.min)
            for photo, _pose_id in photos_to_process:
                photo.taken_at = override_taken_at
        db.commit()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_public_checkin_router.py -k photo_date_override_replaces -v`
Expected: PASS.

- [ ] **Step 5: Run the full public-checkin test file to check for regressions**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_public_checkin_router.py -v`
Expected: all tests PASS (20 previous + 1 new = 21). In particular `test_submit_checkin_uses_photo_exif_date_not_upload_date` must still pass unchanged (it sends no `photo_date`, so `parsed_photo_date` stays `None` and this new block is a no-op for it).

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q`
Expected: same pass count as before this plan, plus the 4 new tests. (There is one pre-existing, unrelated failure — `test_settings_router.py::test_gemini_key_is_scoped_per_account` — not caused by this change; do not attempt to fix it here.)

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/public_checkin.py backend/tests/test_public_checkin_router.py
git commit -m "feat: apply photo_date override to taken_at on check-in submit"
```

---

## Task 3: Frontend — `toIsoDateLocal` date utility

**Files:**
- Modify: `frontend/src/utils/date.ts`
- Test: `frontend/src/utils/date.test.ts` (new file)

- [ ] **Step 1: Write the failing test**

Create `frontend/src/utils/date.test.ts`:

```typescript
// frontend/src/utils/date.test.ts
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { toIsoDateLocal } from "./date.ts";

describe("toIsoDateLocal", () => {
  test("formats a date as local YYYY-MM-DD", () => {
    assert.equal(toIsoDateLocal(new Date(2026, 0, 5)), "2026-01-05");
  });

  test("pads single-digit month and day", () => {
    assert.equal(toIsoDateLocal(new Date(2026, 8, 3)), "2026-09-03");
  });

  test("uses the local calendar date, not UTC (regression: avoids the\n" +
    "  new Date('YYYY-MM-DD').toISOString() day-shift bug)", () => {
    // Late-evening local time must not roll over to the next UTC day.
    const lateEvening = new Date(2026, 5, 15, 23, 30, 0);
    assert.equal(toIsoDateLocal(lateEvening), "2026-06-15");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && node --test src/utils/date.test.ts`
Expected: FAIL with `toIsoDateLocal is not a function` / `does not provide an export named 'toIsoDateLocal'`.

- [ ] **Step 3: Implement `toIsoDateLocal`**

Add to `frontend/src/utils/date.ts` (at the end of the file):

```typescript
/** Formatiert ein Date als lokales YYYY-MM-DD (für <input type="date">
 * value/max-Attribute) - bewusst NICHT über toISOString(), das würde ins
 * UTC-Datum konvertieren und nahe Mitternacht in vielen Zeitzonen auf
 * den falschen Tag springen. */
export function toIsoDateLocal(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && node --test src/utils/date.test.ts`
Expected: PASS (3/3).

- [ ] **Step 5: Run the full frontend test suite and typecheck**

Run: `cd frontend && npm test && npm run typecheck`
Expected: all tests pass, typecheck clean.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/utils/date.ts frontend/src/utils/date.test.ts
git commit -m "feat: add toIsoDateLocal date utility"
```

---

## Task 4: Frontend — pass `photoDate` through the API client

**Files:**
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Update `publicCheckin.submit`**

In `frontend/src/api/client.ts`, find:

```typescript
    submit: (
      token: string,
      payload: {
        weight_kg?: number | null;
        client_note?: string;
        files: File[];
        poseIds: number[];
      }
    ) => {
      const form = new FormData();
      if (payload.weight_kg != null) form.append("weight_kg", String(payload.weight_kg));
      if (payload.client_note) form.append("client_note", payload.client_note);
      for (let i = 0; i < payload.files.length; i++) {
        form.append("files", payload.files[i]);
        form.append("pose_ids", String(payload.poseIds[i]));
      }
      return client
        .post<CheckinSubmission>(`/public/checkin/${token}/submit`, form, {
          headers: { "Content-Type": "multipart/form-data" },
        })
        .then((r) => r.data);
    },
```

Replace with:

```typescript
    submit: (
      token: string,
      payload: {
        weight_kg?: number | null;
        client_note?: string;
        files: File[];
        poseIds: number[];
        photoDate?: string;
      }
    ) => {
      const form = new FormData();
      if (payload.weight_kg != null) form.append("weight_kg", String(payload.weight_kg));
      if (payload.client_note) form.append("client_note", payload.client_note);
      if (payload.photoDate) form.append("photo_date", payload.photoDate);
      for (let i = 0; i < payload.files.length; i++) {
        form.append("files", payload.files[i]);
        form.append("pose_ids", String(payload.poseIds[i]));
      }
      return client
        .post<CheckinSubmission>(`/public/checkin/${token}/submit`, form, {
          headers: { "Content-Type": "multipart/form-data" },
        })
        .then((r) => r.data);
    },
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: clean (no callers pass `photoDate` yet, and it's optional, so this compiles standalone).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat: accept optional photoDate in publicCheckin.submit"
```

---

## Task 5: Frontend — click-to-edit date picker on the check-in page

**Files:**
- Modify: `frontend/src/pages/CheckinSubmit.tsx`

- [ ] **Step 1: Add imports**

At the top of `frontend/src/pages/CheckinSubmit.tsx`, change:

```typescript
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import exifr from "exifr";
import { api, mediaUrl } from "../api/client";
import { parseWeightInput } from "../utils/weight";
import { useBusyOverlay } from "../contexts/BusyOverlayContext";
import { formatDateWithWeek } from "../utils/date";
import { numberedPoseOptionLabel } from "../utils/poseLabel";
import type { Photo } from "../types";
```

to:

```typescript
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import exifr from "exifr";
import { Pencil } from "lucide-react";
import { api, mediaUrl } from "../api/client";
import { parseWeightInput } from "../utils/weight";
import { useBusyOverlay } from "../contexts/BusyOverlayContext";
import { formatDateWithWeek, toIsoDateLocal } from "../utils/date";
import { numberedPoseOptionLabel } from "../utils/poseLabel";
import type { Photo } from "../types";
```

- [ ] **Step 2: Add override state**

Find the end of the `photoDates` EXIF-reading effect:

```typescript
    return () => {
      cancelled = true;
    };
  }, [files]);

  const photoDateLabel =
```

Replace with (inserting the two new state declarations between the effect and `photoDateLabel`):

```typescript
    return () => {
      cancelled = true;
    };
  }, [files]);

  // Manuelle Korrektur des ermittelten Datums (siehe Design-Spec "Check-in:
  // Foto-Datum manuell korrigieren") - überschreibt NUR die Anzeige/den
  // Submit-Wert, das EXIF-Auslesen selbst bleibt unverändert. null = kein
  // Override, ermitteltes Datum gilt weiter.
  const [photoDateOverride, setPhotoDateOverride] = useState<string | null>(null);
  const [editingPhotoDate, setEditingPhotoDate] = useState(false);

  const photoDateLabel =
```

(The next step immediately replaces this `photoDateLabel` block's body — this step only inserts the two new lines above it.)

- [ ] **Step 3: Replace the `photoDateLabel` derivation**

Find:

```typescript
  const photoDateLabel =
    files.length === 0
      ? null
      : photoDates.length === files.length &&
          photoDates.every((d) => isSameCalendarDay(d, photoDates[0]))
        ? formatDateWithWeek(photoDates[0].toISOString())
        : photoDates.length === files.length
          ? "Mixed dates"
          : null; // EXIF-Reads noch nicht fertig - noch kein Label anzeigen
```

Replace with:

```typescript
  const allExifDatesLoaded = files.length > 0 && photoDates.length === files.length;
  const hasUniformPhotoDate =
    allExifDatesLoaded && photoDates.every((d) => isSameCalendarDay(d, photoDates[0]));
  // Einmal korrigiert bleibt das Datum editierbar, auch falls die
  // ursprünglichen EXIF-Daten (rein hypothetisch) nicht uniform waren.
  const isPhotoDateEditable = hasUniformPhotoDate || photoDateOverride !== null;

  const photoDateLabel =
    files.length === 0
      ? null
      : photoDateOverride
        ? formatDateWithWeek(`${photoDateOverride}T12:00:00`)
        : hasUniformPhotoDate
          ? formatDateWithWeek(photoDates[0].toISOString())
          : allExifDatesLoaded
            ? "Mixed dates"
            : null; // EXIF-Reads noch nicht fertig - noch kein Label anzeigen
```

(The override is formatted with a fixed local noon time - `T12:00:00` - so `formatDateWithWeek`'s internal `new Date(iso)` never crosses a UTC day boundary and shows the wrong calendar day in western timezones.)

- [ ] **Step 4: Reset the override on new file selection**

Find the file `<input>`'s `onChange`:

```typescript
              onChange={(e) => {
                setFiles(e.target.files ? Array.from(e.target.files) : []);
                setPhotoPoses({});
                setConfirmation(null);
              }}
```

Replace with:

```typescript
              onChange={(e) => {
                setFiles(e.target.files ? Array.from(e.target.files) : []);
                setPhotoPoses({});
                setConfirmation(null);
                setPhotoDateOverride(null);
                setEditingPhotoDate(false);
              }}
```

- [ ] **Step 5: Reset the override after a successful submit**

Find:

```typescript
    onSuccess: () => {
      hide();
      setConfirmation(photoDateLabel ?? formatDateWithWeek(new Date().toISOString()));
      setWeightKg("");
      setNote("");
      setFiles([]);
      setPhotoPoses({});
      queryClient.invalidateQueries({ queryKey: ["public-checkin", token] });
    },
```

Replace with:

```typescript
    onSuccess: () => {
      hide();
      setConfirmation(photoDateLabel ?? formatDateWithWeek(new Date().toISOString()));
      setWeightKg("");
      setNote("");
      setFiles([]);
      setPhotoPoses({});
      setPhotoDateOverride(null);
      setEditingPhotoDate(false);
      queryClient.invalidateQueries({ queryKey: ["public-checkin", token] });
    },
```

- [ ] **Step 6: Pass the override into the submit call**

Find:

```typescript
  const submitMutation = useMutation({
    mutationFn: () => {
      const parsed = parseWeightInput(weightKg);
      return api.publicCheckin.submit(token!, {
        weight_kg: parsed,
        client_note: note.trim() === "" ? undefined : note.trim(),
        files,
        poseIds: files.map((_, i) => photoPoses[i] as number),
      });
    },
```

Replace with:

```typescript
  const submitMutation = useMutation({
    mutationFn: () => {
      const parsed = parseWeightInput(weightKg);
      return api.publicCheckin.submit(token!, {
        weight_kg: parsed,
        client_note: note.trim() === "" ? undefined : note.trim(),
        files,
        poseIds: files.map((_, i) => photoPoses[i] as number),
        photoDate: photoDateOverride ?? undefined,
      });
    },
```

- [ ] **Step 7: Render the click-to-edit control**

Find:

```typescript
        <div>
          <p className="text-xs text-slate-500">Check-in for</p>
          <h1 className="text-xl font-semibold text-white">{page.client_name}</h1>
          {photoDateLabel && <p className="mt-1 text-sm text-slate-400">{photoDateLabel}</p>}
        </div>
```

Replace with:

```typescript
        <div>
          <p className="text-xs text-slate-500">Check-in for</p>
          <h1 className="text-xl font-semibold text-white">{page.client_name}</h1>
          {photoDateLabel && !editingPhotoDate && (
            isPhotoDateEditable ? (
              <button
                type="button"
                onClick={() => setEditingPhotoDate(true)}
                className="mt-1 flex items-center gap-1.5 text-sm text-slate-400 hover:text-white"
              >
                {photoDateLabel}
                <Pencil className="h-3 w-3" />
              </button>
            ) : (
              <p className="mt-1 text-sm text-slate-400">{photoDateLabel}</p>
            )
          )}
          {editingPhotoDate && (
            <input
              type="date"
              autoFocus
              max={toIsoDateLocal(new Date())}
              defaultValue={
                photoDateOverride ?? (photoDates[0] ? toIsoDateLocal(photoDates[0]) : undefined)
              }
              onChange={(e) => {
                if (e.target.value) setPhotoDateOverride(e.target.value);
                setEditingPhotoDate(false);
              }}
              onBlur={() => setEditingPhotoDate(false)}
              className="mt-1 rounded-lg border border-white/10 bg-black/30 px-2 py-1 text-sm text-white focus:border-accent focus:outline-none"
            />
          )}
        </div>
```

- [ ] **Step 8: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: clean. (If `Pencil` doesn't exist in the installed `lucide-react` version, this will fail with "has no exported member" — if so, replace `Pencil` with `Edit3`, another standard lucide icon, and re-run.)

- [ ] **Step 9: Manual verification in the browser**

Run: `cd frontend && npm run dev` (or use the project's existing dev-server preview flow)

In the browser:
1. Open a client's magic check-in link (`/checkin/<token>`).
2. Select one or more photos with the same EXIF date (or no EXIF, which fall back to the same mtime "now" and are therefore uniform too).
3. Confirm the date label now shows a small pencil icon and is clickable.
4. Click it — confirm a native date picker opens, pre-filled with the shown date, and cannot go past today (max).
5. Pick an earlier date — confirm the label updates to the new date (with pencil icon still shown, still clickable).
6. Submit the check-in — confirm success, and that the submission lands under the corrected date (e.g. check the client's timeline/compare view as the coach, or inspect the DB `Photo.taken_at`).
7. Repeat with photos that have genuinely different EXIF dates ("Mixed dates") — confirm the label is NOT clickable in that case.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/pages/CheckinSubmit.tsx
git commit -m "feat: let clients correct the detected check-in photo date"
```

---

## Task 6: Final verification and branch finish

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q`
Expected: same result as Task 2 Step 6 (all green except the pre-existing, unrelated `test_gemini_key_is_scoped_per_account` failure).

- [ ] **Step 2: Run the full frontend test suite and typecheck**

Run: `cd frontend && npm test && npm run typecheck`
Expected: all green.

- [ ] **Step 3: Use the finishing-a-development-branch skill**

Follow `superpowers:finishing-a-development-branch` to merge/push per the user's established workflow (merge to `dev` + push to `origin/dev`).
