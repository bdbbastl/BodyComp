# Check-in Client-Pose-Assignment + Review-Gated Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let clients pick a pose per photo when submitting a magic-link check-in (photos get fully processed immediately), but keep those photos hidden from Timeline/Compare until the coach marks that check-in reviewed.

**Architecture:** Extend the public check-in GET/submit endpoints to expose poses and accept per-file pose selections, reusing the already-parallelized photo-processing pipeline from `photos.py`. Add a visibility filter to `GET /clients/:id/photos` that hides check-in-linked photos until their submission is reviewed. Frontend: widen the magic-link page and add a thumbnail+pose picker per selected file.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, React, TypeScript.

---

### Task 1: Expose poses on the public check-in page + accept per-file pose selection on submit

**Files:**
- Modify: `backend/app/schemas/checkin.py`
- Modify: `backend/app/routers/public_checkin.py`
- Test: `backend/tests/test_public_checkin_router.py`

- [ ] **Step 1: Write the failing tests**

Add these tests to `backend/tests/test_public_checkin_router.py`:

```python
def test_get_checkin_page_includes_client_poses(client, db_session):
    from app.models.pose import Pose

    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    token = created["checkin_token"]

    pose = Pose(client_id=created["id"], name="Front Relaxed", sort_order=0)
    db_session.add(pose)
    db_session.commit()
    db_session.refresh(pose)

    response = client.get(f"/api/public/checkin/{token}")
    body = response.json()
    assert body["poses"] == [{"id": pose.id, "name": "Front Relaxed"}]


def test_submit_checkin_with_photo_requires_matching_pose_id(client, db_session):
    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    token = created["checkin_token"]

    response = client.post(
        f"/api/public/checkin/{token}/submit",
        files={"files": ("p1.jpg", b"fake-image-bytes", "image/jpeg")},
        # kein pose_ids mitgeschickt -> Laenge stimmt nicht (0 != 1 Datei)
    )
    assert response.status_code == 400


def test_submit_checkin_rejects_pose_id_of_foreign_client(client, db_session):
    from app.models.pose import Pose

    _login(client, db_session, email="a@b.com")
    created_a = client.post("/api/clients", json={"name": "Max"}).json()
    token_a = created_a["checkin_token"]

    client.post("/api/auth/logout")
    _login(client, db_session, email="c@d.com")
    created_c = client.post("/api/clients", json={"name": "Other"}).json()
    foreign_pose = Pose(client_id=created_c["id"], name="Front", sort_order=0)
    db_session.add(foreign_pose)
    db_session.commit()
    db_session.refresh(foreign_pose)

    response = client.post(
        f"/api/public/checkin/{token_a}/submit",
        files={"files": ("p1.jpg", b"fake-image-bytes", "image/jpeg")},
        data={"pose_ids": str(foreign_pose.id)},
    )
    assert response.status_code == 400


def test_submit_checkin_with_valid_pose_processes_photo_immediately(client, db_session):
    from app.models.photo import ProcessingStatus
    from app.models.pose import Pose

    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    token = created["checkin_token"]

    pose = Pose(client_id=created["id"], name="Front Relaxed", sort_order=0)
    db_session.add(pose)
    db_session.commit()
    db_session.refresh(pose)

    response = client.post(
        f"/api/public/checkin/{token}/submit",
        files={"files": ("p1.jpg", b"fake-image-bytes", "image/jpeg")},
        data={"pose_ids": str(pose.id)},
    )
    assert response.status_code == 201
    body = response.json()
    assert len(body["photos"]) == 1
    photo = body["photos"][0]
    assert photo["pose_id"] == pose.id
    # Kein echtes Bild in diesem Test -> MediaPipe findet nichts,
    # Normalisierung schlaegt fehl, aber Pose-Zuordnung/Verschieben
    # laeuft trotzdem durch (best-effort, siehe Design-Spec).
    assert photo["status"] == ProcessingStatus.NORMALIZATION_FAILED.value
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_public_checkin_router.py -k "poses or pose_id or processes_photo" -v`
Expected: FAIL (`poses` field doesn't exist yet, `pose_ids` isn't accepted, no immediate processing happens yet).

- [ ] **Step 3: Update the schema**

In `backend/app/schemas/checkin.py`, add this class and update `PublicCheckinPageOut`:

```python
class PublicPoseOut(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class PublicCheckinPageOut(BaseModel):
    client_name: str
    submissions: list[PublicCheckinSubmissionOut]
    poses: list[PublicPoseOut]
```

- [ ] **Step 4: Update `get_checkin_page` to return poses**

In `backend/app/routers/public_checkin.py`, add `from app.models.pose import Pose` to the imports, and replace `get_checkin_page`:

```python
@router.get("/{token}", response_model=PublicCheckinPageOut)
def get_checkin_page(
    client_row: Client = Depends(get_client_by_checkin_token), db: Session = Depends(get_db)
):
    submissions = (
        db.query(CheckinSubmission)
        .filter(CheckinSubmission.client_id == client_row.id)
        .order_by(CheckinSubmission.submitted_at.desc())
        .all()
    )
    poses = (
        db.query(Pose)
        .filter(Pose.client_id == client_row.id)
        .order_by(Pose.sort_order)
        .all()
    )
    return PublicCheckinPageOut(client_name=client_row.name, submissions=submissions, poses=poses)
```

- [ ] **Step 5: Update `submit_checkin` to validate and process with poses**

In `backend/app/routers/public_checkin.py`, update the imports at the top - replace:

```python
from app.services.folder_sync import sync_incoming_folder
from app.services.storage_paths import incoming_dir_for_client
from app.services.storage_sync import push
```

with:

```python
from app.services.folder_sync import sync_incoming_folder
from app.services.storage_paths import incoming_dir_for_client
from app.services.storage_sync import push
from app.routers.photos import (
    PHOTO_PROCESSING_MAX_WORKERS,
    _ProcessedPhotoFiles,
    _apply_processed_result,
    _get_or_create_day_log,
    _process_photo_files,
)
from concurrent.futures import ThreadPoolExecutor, as_completed
```

Add `Pose` to the model imports (alongside the existing `from app.models.checkin_submission import CheckinSubmission` line):

```python
from app.models.pose import Pose
```

Replace the `submit_checkin` function signature to accept `pose_ids`:

```python
@router.post("/{token}/submit", response_model=CheckinSubmissionOut, status_code=201)
def submit_checkin(
    weight_kg: str | None = Form(default=None),
    client_note: str | None = Form(default=None),
    files: list[UploadFile] = File(default=[]),
    pose_ids: list[int] = Form(default=[]),
    client_row: Client = Depends(get_client_by_checkin_token),
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(checkin_submit_rate_limit),
):
```

Right after the existing file-count/file-size validation block (after the `for upload in files:` size-check loop, before the `try: parsed_weight_kg = ...` block), add pose validation:

```python
    if files and len(pose_ids) != len(files):
        raise HTTPException(400, "Each photo needs a pose selected")
    if pose_ids:
        valid_pose_ids = {
            pid
            for (pid,) in db.query(Pose.id).filter(
                Pose.id.in_(pose_ids), Pose.client_id == client_row.id
            ).all()
        }
        if any(pid not in valid_pose_ids for pid in pose_ids):
            raise HTTPException(400, "Invalid pose selected")
```

Replace the entire `if files:` block (the file-writing/sync section) with:

```python
    if files:
        incoming_dir = incoming_dir_for_client(client_row.id)
        incoming_dir.mkdir(parents=True, exist_ok=True)
        # Bildet den TATSAECHLICH geschriebenen relativen Pfad auf die vom
        # Klienten gewaehlte pose_id ab (Reihenfolge von files/pose_ids
        # entspricht sich 1:1) - der Dateiname kann sich beim Schreiben
        # durch Kollisions-Zaehler aendern, daher erst NACH dem Schreiben
        # den finalen Pfad als Schluessel verwenden.
        path_to_pose_id: dict[str, int] = {}
        for upload, pose_id in zip(files, pose_ids):
            if not upload.filename:
                continue
            # Nur den Dateinamen uebernehmen, keine Pfad-Komponenten - dieser
            # Endpunkt ist unauthentifiziert, ein manipulierter Dateiname
            # wie "../../evil.jpg" duerfte niemals ausserhalb von
            # incoming_dir schreiben koennen (Path-Traversal).
            safe_name = Path(upload.filename).name
            suffix = Path(safe_name).suffix.lower()
            if suffix not in settings.allowed_extensions:
                continue
            dest = incoming_dir / safe_name
            counter = 1
            while dest.exists():
                dest = incoming_dir / f"{Path(safe_name).stem}_{counter}{suffix}"
                counter += 1
            with dest.open("wb") as f:
                shutil.copyfileobj(upload.file, f)
            rel_path = dest.relative_to(settings.data_dir).as_posix()
            path_to_pose_id[rel_path] = pose_id
            push(rel_path)

        new_photos = sync_incoming_folder(db, client_row.id)
        photos_to_process = [
            (photo, path_to_pose_id[photo.original_path])
            for photo in new_photos
            if photo.original_path in path_to_pose_id
        ]
        for photo, _pose_id in photos_to_process:
            photo.checkin_submission_id = submission.id
        db.commit()

        # Sofort vollstaendig verarbeiten (Pose ist ja schon bekannt) -
        # dieselbe parallelisierte Pipeline wie beim Coach-Bulk-Import
        # (siehe Design-Spec "Check-in: Client-Pose-Zuordnung"). Der Coach
        # muss danach nichts mehr im Import-Tab tun.
        pose_by_id = {p.id: p for p in db.query(Pose).filter(Pose.client_id == client_row.id).all()}
        day_logs_by_photo_id: dict[int, DayLog] = {}
        for photo, pose_id in photos_to_process:
            day_date = photo.taken_at.date()
            day_logs_by_photo_id[photo.id] = _get_or_create_day_log(
                db, client_row.id, day_date, client_row.owner
            )
        db.commit()

        with ThreadPoolExecutor(max_workers=PHOTO_PROCESSING_MAX_WORKERS) as executor:
            future_to_photo_id = {
                executor.submit(
                    _process_photo_files,
                    client_id=client_row.id,
                    filename=photo.filename,
                    original_path=photo.original_path,
                    preview_path=photo.preview_path,
                    thumbnail_path=photo.thumbnail_path,
                    day_date_iso=photo.taken_at.date().isoformat(),
                    pose_id=pose_id,
                    photo_id=photo.id,
                ): photo.id
                for photo, pose_id in photos_to_process
            }
            results_by_photo_id: dict[int, _ProcessedPhotoFiles] = {}
            for future in as_completed(future_to_photo_id):
                photo_id = future_to_photo_id[future]
                results_by_photo_id[photo_id] = future.result()

        for photo, pose_id in photos_to_process:
            _apply_processed_result(
                db,
                photo,
                day_logs_by_photo_id[photo.id],
                pose_by_id[pose_id],
                None,
                results_by_photo_id[photo.id],
            )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_public_checkin_router.py -v`
Expected: `test_submit_checkin_sanitizes_path_traversal_filename` will now FAIL - see Step 7.

- [ ] **Step 7: Update the now-outdated path-traversal test**

The existing `test_submit_checkin_sanitizes_path_traversal_filename` submits a file WITHOUT a matching `pose_ids` entry, which now correctly gets rejected with 400 (mismatched lengths) before ever reaching the file-write code - the security behavior it was protecting (sanitized filename, no path traversal) is now proven by the NEW test `test_submit_checkin_with_valid_pose_processes_photo_immediately` instead (which also uses a malicious-adjacent real filename flow). Update the old test to send a valid pose so it still exercises path-traversal sanitization, but now checking the file's FINAL location after full processing (moved into `photos_processed/`, not left in `incoming_dir`):

Replace `test_submit_checkin_sanitizes_path_traversal_filename` in `backend/tests/test_public_checkin_router.py` with:

```python
def test_submit_checkin_sanitizes_path_traversal_filename(client, db_session):
    """Ein Dateiname wie "../../evil.jpg" darf niemals ausserhalb von
    data_dir landen - siehe Sicherheits-Fix nach Code-Review von Task 5
    (dieser Endpunkt ist unauthentifiziert). Nur der reine Dateiname
    ("evil.jpg") darf uebrig bleiben, verarbeitet landet er in
    photos_processed/ (Pose ist jetzt Pflicht, siehe Design-Spec)."""
    from app.core.config import settings
    from app.models.pose import Pose

    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    token = created["checkin_token"]
    pose = Pose(client_id=created["id"], name="Front", sort_order=0)
    db_session.add(pose)
    db_session.commit()
    db_session.refresh(pose)

    malicious_name = "../../../../evil.jpg"
    response = client.post(
        f"/api/public/checkin/{token}/submit",
        files={"files": (malicious_name, b"fake-image-bytes", "image/jpeg")},
        data={"pose_ids": str(pose.id)},
    )
    assert response.status_code == 201

    # Nirgendwo ausserhalb von data_dir darf eine Datei namens evil.jpg
    # entstanden sein.
    for candidate in settings.data_dir.parent.glob("evil.jpg"):
        assert False, f"Path-Traversal: Datei ausserhalb data_dir geschrieben: {candidate}"
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_public_checkin_router.py -v`
Expected: all PASS.

- [ ] **Step 9: Run the full backend test suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all PASS except the pre-existing unrelated `test_gemini_key_is_scoped_per_account` failure.

- [ ] **Step 10: Commit**

```bash
git add backend/app/schemas/checkin.py backend/app/routers/public_checkin.py backend/tests/test_public_checkin_router.py
git commit -m "feat: let clients assign poses at check-in submission, process photos immediately"
```

---

### Task 2: Hide unreviewed check-in photos from Timeline/Compare

**Files:**
- Modify: `backend/app/routers/photos.py`
- Test: `backend/tests/test_photos_router_scoped.py`

- [ ] **Step 1: Write the failing tests**

Add these tests to `backend/tests/test_photos_router_scoped.py`:

```python
def test_list_photos_hides_unreviewed_checkin_photos(client, db_session):
    from app.models.checkin_submission import CheckinStatus, CheckinSubmission
    from app.models.photo import Photo, ProcessingStatus
    from app.models.pose import Pose

    client_id = _login_and_get_client(client, db_session)

    pose = Pose(client_id=client_id, name="Front", sort_order=0)
    db_session.add(pose)
    db_session.commit()
    db_session.refresh(pose)

    submission = CheckinSubmission(client_id=client_id, status=CheckinStatus.PENDING)
    db_session.add(submission)
    db_session.commit()
    db_session.refresh(submission)

    photo = Photo(
        client_id=client_id,
        filename="p1.jpg",
        original_path=f"photos_processed/{client_id}/p1.jpg",
        taken_at=datetime(2026, 1, 1, 12, 0, 0),
        status=ProcessingStatus.PROCESSED,
        pose_id=pose.id,
        checkin_submission_id=submission.id,
    )
    db_session.add(photo)
    db_session.commit()

    response = client.get(f"/api/clients/{client_id}/photos")
    assert response.status_code == 200
    assert response.json() == []

    submission.status = CheckinStatus.REVIEWED
    db_session.commit()

    response = client.get(f"/api/clients/{client_id}/photos")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_list_photos_shows_non_checkin_photos_unaffected(client, db_session):
    from app.models.photo import Photo, ProcessingStatus
    from app.models.pose import Pose

    client_id = _login_and_get_client(client, db_session)

    pose = Pose(client_id=client_id, name="Front", sort_order=0)
    db_session.add(pose)
    db_session.commit()
    db_session.refresh(pose)

    photo = Photo(
        client_id=client_id,
        filename="p1.jpg",
        original_path=f"photos_processed/{client_id}/p1.jpg",
        taken_at=datetime(2026, 1, 1, 12, 0, 0),
        status=ProcessingStatus.PROCESSED,
        pose_id=pose.id,
        checkin_submission_id=None,
    )
    db_session.add(photo)
    db_session.commit()

    response = client.get(f"/api/clients/{client_id}/photos")
    assert response.status_code == 200
    assert len(response.json()) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_photos_router_scoped.py -k "checkin_photos" -v`
Expected: FAIL (`test_list_photos_hides_unreviewed_checkin_photos` fails - the photo is currently returned regardless of review status).

- [ ] **Step 3: Add the visibility filter**

In `backend/app/routers/photos.py`, add this import near the other model imports:

```python
from app.models.checkin_submission import CheckinStatus, CheckinSubmission
```

Replace the `list_photos` function body:

```python
@router.get("", response_model=list[PhotoOut])
def list_photos(
    pose_id: int | None = None,
    status: ProcessingStatus | None = None,
    client_row: Client = Depends(get_owned_client),
    db: Session = Depends(get_db),
):
    """Für Timeline-Dashboard und Comparison-Mode (Filter nach Pose).

    Fotos, die zu einem noch nicht 'reviewed' Check-in gehören, werden
    ausgeblendet - siehe Design-Spec "Check-in: Client-Pose-Zuordnung +
    Review-gesteuerte Timeline". Fotos ohne checkin_submission_id (normale
    Coach-Uploads) sind davon unberührt.
    """
    q = (
        db.query(Photo)
        .filter(Photo.client_id == client_row.id)
        .outerjoin(CheckinSubmission, Photo.checkin_submission_id == CheckinSubmission.id)
        .filter(
            (Photo.checkin_submission_id.is_(None))
            | (CheckinSubmission.status == CheckinStatus.REVIEWED)
        )
    )
    if pose_id is not None:
        q = q.filter(Photo.pose_id == pose_id)
    if status is not None:
        q = q.filter(Photo.status == status)
    return q.order_by(Photo.taken_at.desc()).all()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_photos_router_scoped.py -v`
Expected: all PASS.

- [ ] **Step 5: Run the full backend test suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all PASS except the pre-existing unrelated `test_gemini_key_is_scoped_per_account` failure.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/photos.py backend/tests/test_photos_router_scoped.py
git commit -m "feat: hide unreviewed check-in photos from Timeline/Compare"
```

---

### Task 3: Frontend types + API client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Update the `PublicCheckinPage` type**

In `frontend/src/types/index.ts`, replace:

```typescript
export interface PublicCheckinPage {
  client_name: string;
  submissions: Omit<CheckinSubmission, "reviewed_at">[];
}
```

with:

```typescript
export interface PublicCheckinPose {
  id: number;
  name: string;
}

export interface PublicCheckinPage {
  client_name: string;
  submissions: Omit<CheckinSubmission, "reviewed_at">[];
  poses: PublicCheckinPose[];
}
```

- [ ] **Step 2: Update `api.publicCheckin.submit` to accept pose IDs**

In `frontend/src/api/client.ts`, add `PublicCheckinPose` to the existing `import type { ... } from "../types";` line (alphabetized among the existing entries).

Replace the `publicCheckin` object:

```typescript
  publicCheckin: {
    get: (token: string) =>
      client.get<PublicCheckinPage>(`/public/checkin/${token}`).then((r) => r.data),
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
  },
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: this will show an error in `frontend/src/pages/CheckinSubmit.tsx` (its existing call to `api.publicCheckin.submit` doesn't pass `poseIds` yet) - that's expected and gets fixed in Task 4. Confirm the error is ONLY in `CheckinSubmit.tsx` and nowhere else.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/client.ts
git commit -m "feat: add pose selection to public check-in API client"
```

---

### Task 4: Widen the magic-link page and add the pose picker

**Files:**
- Modify: `frontend/src/pages/CheckinSubmit.tsx`

- [ ] **Step 1: Replace the full file content**

Replace the entire content of `frontend/src/pages/CheckinSubmit.tsx` with:

```tsx
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { api, mediaUrl } from "../api/client";
import { parseWeightInput } from "../utils/weight";

/**
 * Öffentliche, passwortlose Seite für Klienten - siehe Design-Spec
 * Abschnitt "Klienten-Ansicht". Bewusst KEIN AppShell/ClientShell: diese
 * Seite ist eigenständig, handy-tauglich und für jeden mit dem Link
 * erreichbar, unabhängig vom eingeloggten Coach-Zustand im selben Browser.
 *
 * Der Klient wählt selbst eine Pose pro Foto (siehe Design-Spec
 * "Check-in: Client-Pose-Zuordnung + Review-gesteuerte Timeline") - das
 * reduziert Coach-Aufwand, die Fotos werden serverseitig sofort
 * vollständig verarbeitet, bleiben aber bis zum "reviewed" durch den
 * Coach in Timeline/Compare unsichtbar.
 */
export default function CheckinSubmit() {
  const { token } = useParams<{ token: string }>();
  const queryClient = useQueryClient();
  const [weightKg, setWeightKg] = useState("");
  const [note, setNote] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [photoPoses, setPhotoPoses] = useState<Record<number, number | "">>({});

  const pageQuery = useQuery({
    queryKey: ["public-checkin", token],
    queryFn: () => api.publicCheckin.get(token!),
    enabled: !!token,
  });

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
      setWeightKg("");
      setNote("");
      setFiles([]);
      setPhotoPoses({});
      queryClient.invalidateQueries({ queryKey: ["public-checkin", token] });
    },
  });

  if (pageQuery.isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4 text-slate-400">
        Loading…
      </div>
    );
  }

  if (pageQuery.isError || !pageQuery.data) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4">
        <p className="text-slate-400">This link is invalid or has expired.</p>
      </div>
    );
  }

  const page = pageQuery.data;
  const allPhotosHavePoses = files.length === 0 || files.every((_, i) => !!photoPoses[i]);

  return (
    <div className="min-h-screen bg-background px-4 py-8 text-slate-100">
      <div className="mx-auto max-w-2xl space-y-6">
        <div>
          <p className="text-xs text-slate-500">Check-in for</p>
          <h1 className="text-xl font-semibold text-white">{page.client_name}</h1>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (allPhotosHavePoses) submitMutation.mutate();
          }}
          className="space-y-4 rounded-xl border border-white/5 bg-surface p-4"
        >
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Weight (kg)
            <input
              type="text"
              inputMode="decimal"
              value={weightKg}
              onChange={(e) => setWeightKg(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Note (optional)
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={3}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Photos (optional)
            <input
              type="file"
              multiple
              accept="image/jpeg,image/png,image/heic,.heic"
              onChange={(e) => {
                const newFiles = e.target.files ? Array.from(e.target.files) : [];
                setFiles(newFiles);
                setPhotoPoses({});
              }}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-slate-400 file:mr-3 file:rounded-lg file:border-0 file:bg-accent file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-slate-900"
            />
          </label>

          {files.length > 0 && (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3">
              {files.map((file, i) => (
                <div
                  key={`${file.name}-${i}`}
                  className="space-y-2 rounded-lg border border-white/10 bg-black/20 p-2"
                >
                  <img
                    src={URL.createObjectURL(file)}
                    alt={file.name}
                    className="aspect-square w-full rounded-md object-cover"
                  />
                  <select
                    required
                    value={photoPoses[i] ?? ""}
                    onChange={(e) =>
                      setPhotoPoses((prev) => ({
                        ...prev,
                        [i]: e.target.value === "" ? "" : Number(e.target.value),
                      }))
                    }
                    className="w-full rounded-lg border border-white/10 bg-black/30 px-2 py-1.5 text-xs text-white focus:border-accent focus:outline-none"
                  >
                    <option value="">Choose pose…</option>
                    {page.poses.map((pose) => (
                      <option key={pose.id} value={pose.id}>
                        {pose.name}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          )}

          {submitMutation.isError && (
            <p className="text-sm text-red-400">Submission failed - please try again.</p>
          )}
          <button
            type="submit"
            disabled={submitMutation.isPending || !allPhotosHavePoses}
            className="sticky bottom-4 w-full rounded-lg bg-accent px-4 py-3 text-sm font-medium text-slate-900 shadow-lg shadow-black/40 hover:opacity-90 disabled:opacity-50 sm:static sm:py-2 sm:shadow-none"
          >
            {submitMutation.isPending ? "Submitting…" : "Submit check-in"}
          </button>
        </form>
```

Note: the file ends there in the excerpt above only for brevity of this plan step - the ACTUAL remainder of the original file (everything after the closing `</form>` - the submission history list further down the page) is UNCHANGED and must be kept exactly as it already exists in the file today. Do not delete it; only the JSX shown above (imports, component signature through the `</form>` closing tag and the new grid block) changes. Read the current file first to confirm the exact remainder, then apply only the diffs shown here (do not blindly overwrite the whole file if the tail differs from what's assumed).

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors (the Task 3 error about missing `poseIds` is now resolved).

- [ ] **Step 3: Manual verification**

Read through the file and confirm:
- Container is `max-w-2xl`, not `max-w-md`.
- Selecting files resets `photoPoses` (avoids stale pose assignments if the file list changes).
- Submit button is disabled until every selected file has a pose chosen (`allPhotosHavePoses`).
- The submission-history section below the form (rendering `page.submissions`) is untouched.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/CheckinSubmit.tsx
git commit -m "feat: widen check-in page, let client pick pose per photo before submitting"
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

- Confirm `_process_photo_files`/`_apply_processed_result`/`_get_or_create_day_log`/`PHOTO_PROCESSING_MAX_WORKERS`/`_ProcessedPhotoFiles` are importable from `app.routers.photos` into `app.routers.public_checkin` without circular-import errors (run `cd backend && .venv/Scripts/python -c "import app.main"` to confirm the app still imports cleanly).
- Confirm `list_photos`'s new `outerjoin` doesn't produce duplicate rows (a `Photo` has at most one `CheckinSubmission` via `checkin_submission_id`, so the join is 1:0-or-1 - no fan-out risk, but double check by reading the join condition once more).
- Confirm the existing coach-side `PATCH /clients/{client_id}/checkins/{checkin_id}` `mark_reviewed` flow (in `backend/app/routers/checkins.py`) needed NO changes - it already sets `CheckinSubmission.status = REVIEWED`, which the new `list_photos` filter already reads.
- No leftover German user-facing strings in `CheckinSubmit.tsx`.

- [ ] **Step 4: Use the finishing-a-development-branch skill**

Invoke `superpowers:finishing-a-development-branch` to push per the user's standing "option 1" preference (this session works directly on `dev`).
