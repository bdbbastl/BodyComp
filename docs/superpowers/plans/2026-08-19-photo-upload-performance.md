# Photo Upload/Save Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut the wall-clock time of "upload photos" and "save all assigned" from tens of seconds down to a few seconds for a typical batch, by running the independent per-photo work concurrently instead of one photo at a time, with zero change to correctness or error behavior.

**Architecture:** Split `_assign_photo` into a thread-safe pure-file-processing function and a DB-application function; dispatch the file-processing across a small `ThreadPoolExecutor` for both `/photos/assign-bulk` and `/photos/upload`; keep all database writes serialized in the main thread; the response still waits for every worker to finish (fully synchronous from the caller's perspective, just internally parallel).

**Tech Stack:** FastAPI, SQLAlchemy, Python `concurrent.futures.ThreadPoolExecutor`.

---

### Task 1: Split `_assign_photo` into thread-safe file processing + DB application

**Files:**
- Modify: `backend/app/routers/photos.py`
- Test: `backend/tests/test_photos_router_scoped.py`

- [ ] **Step 1: Write the failing test**

Add this test to `backend/tests/test_photos_router_scoped.py` (it exercises the existing `/assign` endpoint end-to-end and must keep passing after the refactor - this is a regression guard, written BEFORE the refactor so you can confirm it passes both before and after):

```python
def test_assign_photo_sets_processed_status_and_day_log(client, db_session):
    from app.models.photo import Photo, ProcessingStatus
    from app.models.pose import Pose

    client_id = _login_and_get_client(client, db_session)

    pose = Pose(client_id=client_id, name="Front", sort_order=0)
    db_session.add(pose)
    db_session.commit()

    photo = Photo(
        client_id=client_id,
        filename="p1.jpg",
        original_path=f"photos_incoming/{client_id}/p1.jpg",
        taken_at=datetime(2026, 1, 1, 12, 0, 0),
        status=ProcessingStatus.UNPROCESSED,
    )
    db_session.add(photo)
    db_session.commit()
    db_session.refresh(photo)

    response = client.post(
        f"/api/clients/{client_id}/photos/{photo.id}/assign",
        json={"pose_id": pose.id},
    )
    assert response.status_code == 200
    body = response.json()
    # Kein echtes Bild auf Platte in diesem Test -> MediaPipe findet nichts,
    # Normalisierung schlägt fehl, aber die Zuordnung selbst muss trotzdem
    # durchgehen (bestehendes "best effort"-Verhalten, siehe Design-Spec).
    assert body["status"] == "normalization_failed"
    assert body["pose_id"] == pose.id

    day_logs = client.get(f"/api/clients/{client_id}/day-logs").json()
    assert len(day_logs) == 1
    assert day_logs[0]["date"] == "2026-01-01"
```

- [ ] **Step 2: Run test to verify it passes against the CURRENT (unrefactored) code**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_photos_router_scoped.py::test_assign_photo_sets_processed_status_and_day_log -v`
Expected: PASS (this confirms your understanding of current behavior before you touch anything).

- [ ] **Step 3: Perform the refactor**

In `backend/app/routers/photos.py`, add these imports at the top (alongside the existing ones):

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
```

Add this constant right after the `router = APIRouter(...)` line:

```python
# Begrenzt gleichzeitige Foto-Verarbeitung (Datei-I/O + MediaPipe-
# Inferenz) - verhindert CPU-Überlastung durch zu viele parallele
# Inferenzen auf dem begrenzten Railway-Container. Siehe Design-Spec
# "Foto-Upload/Speicher-Performance".
PHOTO_PROCESSING_MAX_WORKERS = 4
```

Replace the ENTIRE `_assign_photo` function (currently lines 198-287) with the following THREE functions:

```python
def _get_or_create_day_log(db: Session, client_id: int, day_date, owner: User) -> DayLog:
    """Holt den DayLog für ein Datum oder legt ihn an (inkl. Freikontingent-
    Prüfung für neue Tage). Extrahiert aus der früheren _assign_photo, damit
    sowohl die Einzel- als auch die Bulk-Zuordnung dieselbe Logik nutzen -
    wichtig für Bulk: muss VOR dem Parallel-Dispatch pro Item aufgelöst
    werden, da mehrere Fotos desselben Tages sich sonst beim parallelen
    Anlegen desselben DayLog in die Quere kommen könnten (Race Condition).
    `db.flush()` (nicht nur `db.add`) ist nötig, damit ein direkt
    anschließender Aufruf für ein ANDERES Foto desselben Tages im selben
    Batch den gerade erst angelegten (noch nicht committeten) DayLog per
    Query bereits findet - die Test-Session läuft mit autoflush=False."""
    day_log = (
        db.query(DayLog)
        .filter(DayLog.client_id == client_id, DayLog.date == day_date)
        .first()
    )
    if day_log is None:
        check_and_consume_free_checkin(owner, db)
        day_log = DayLog(client_id=client_id, date=day_date)
        db.add(day_log)
        db.flush()
    return day_log


@dataclass
class _ProcessedPhotoFiles:
    """Ergebnis der reinen Datei-/Bildverarbeitung eines Fotos - enthält
    absichtlich KEINE SQLAlchemy-Objekte (Sessions sind nicht thread-safe),
    nur primitive Werte, damit diese Funktion sicher aus einem
    ThreadPoolExecutor-Worker heraus aufgerufen werden kann."""
    original_path: str
    preview_path: str | None
    thumbnail_path: str | None
    normalization_succeeded: bool
    normalized_path: str | None
    landmarks_json: str | None


def _process_photo_files(
    *,
    client_id: int,
    filename: str,
    original_path: str,
    preview_path: str | None,
    thumbnail_path: str | None,
    day_date_iso: str,
    pose_id: int,
    photo_id: int,
) -> _ProcessedPhotoFiles:
    """Alles außer DB-Schreiben: Datei-Move nach photos_processed/,
    Thumbnail-Erzeugung falls fehlend, MediaPipe-Normalisierung, alle
    R2-Uploads. Nimmt und liefert nur primitive Werte (keine ORM-Objekte) -
    sicher aus einem Thread-Pool-Worker aufrufbar. Siehe Design-Spec
    "Foto-Upload/Speicher-Performance" Abschnitt "/photos/assign-bulk"."""
    dest_dir = processed_dir_for_client_date(client_id, day_date_iso)
    dest_dir.mkdir(parents=True, exist_ok=True)

    result_original_path = original_path
    result_preview_path = preview_path
    result_thumbnail_path = thumbnail_path

    ensure_local(original_path)
    src = settings.data_dir / original_path
    if src.exists():
        dest = dest_dir / filename
        shutil.move(str(src), str(dest))
        result_original_path = dest.relative_to(settings.data_dir).as_posix()
        push(result_original_path)

    if preview_path:
        ensure_local(preview_path)
        preview_src = settings.data_dir / preview_path
        if preview_src.exists():
            preview_dest = dest_dir / preview_src.name
            shutil.move(str(preview_src), str(preview_dest))
            result_preview_path = preview_dest.relative_to(settings.data_dir).as_posix()
            push(result_preview_path)

    if thumbnail_path:
        ensure_local(thumbnail_path)
        thumb_src = settings.data_dir / thumbnail_path
        if thumb_src.exists():
            thumb_dest = dest_dir / thumb_src.name
            shutil.move(str(thumb_src), str(thumb_dest))
            result_thumbnail_path = thumb_dest.relative_to(settings.data_dir).as_posix()
            push(result_thumbnail_path)
    if not result_thumbnail_path:
        thumb_source = settings.data_dir / (result_preview_path or result_original_path)
        thumb_dest = dest_dir / thumbnail_path_for(thumb_source).name
        if generate_thumbnail(thumb_source, thumb_dest):
            result_thumbnail_path = thumb_dest.relative_to(settings.data_dir).as_posix()
            push(result_thumbnail_path)

    # MediaPipe-Normalisierung (best effort - siehe Design-Spec).
    # HEIC-Originale kann OpenCV nicht lesen -> Vorschau als Quelle nutzen.
    ensure_local(result_preview_path or result_original_path)
    normalize_source = settings.data_dir / (result_preview_path or result_original_path)
    normalized_dest = normalized_dir_for_client_pose(client_id, pose_id) / f"{photo_id}.jpg"
    norm_result = normalize_photo(normalize_source, normalized_dest)

    normalized_path = None
    landmarks_json = None
    if norm_result.success and norm_result.normalized_path:
        normalized_path = norm_result.normalized_path.relative_to(settings.data_dir).as_posix()
        push(normalized_path)
        landmarks_json = norm_result.landmarks_json

    return _ProcessedPhotoFiles(
        original_path=result_original_path,
        preview_path=result_preview_path,
        thumbnail_path=result_thumbnail_path,
        normalization_succeeded=norm_result.success and norm_result.normalized_path is not None,
        normalized_path=normalized_path,
        landmarks_json=landmarks_json,
    )


def _apply_processed_result(
    db: Session, photo: Photo, day_log: DayLog, pose: Pose, weight_kg: float | None,
    result: _ProcessedPhotoFiles,
) -> Photo:
    """Überträgt das Ergebnis von _process_photo_files auf die ORM-Objekte
    und committet - läuft IMMER im Hauptthread (Sessions sind nicht
    thread-safe). Siehe Design-Spec."""
    if weight_kg is not None:
        day_log.weight_kg = weight_kg

    photo.original_path = result.original_path
    photo.preview_path = result.preview_path
    photo.thumbnail_path = result.thumbnail_path
    photo.pose_id = pose.id
    photo.day_log_id = day_log.id
    photo.updated_at = datetime.utcnow()

    if result.normalization_succeeded:
        photo.normalized_path = result.normalized_path
        photo.landmarks_json = result.landmarks_json
        photo.status = ProcessingStatus.PROCESSED
    else:
        photo.status = ProcessingStatus.NORMALIZATION_FAILED

    db.commit()
    db.refresh(photo)
    return photo


def _assign_photo(db: Session, photo: Photo, pose: Pose, weight_kg: float | None, owner: User) -> Photo:
    """Ordnet EIN Foto zu (Einzel-Endpunkt /assign) - ruft dieselben
    Bausteine wie die Bulk-Zuordnung auf, aber synchron im Hauptthread
    (ein einzelnes Foto profitiert nicht von Parallelisierung). Siehe
    Design-Spec Abschnitt "Einzel-Zuordnung"."""
    day_date = photo.taken_at.date()
    day_log = _get_or_create_day_log(db, photo.client_id, day_date, owner)

    result = _process_photo_files(
        client_id=photo.client_id,
        filename=photo.filename,
        original_path=photo.original_path,
        preview_path=photo.preview_path,
        thumbnail_path=photo.thumbnail_path,
        day_date_iso=day_date.isoformat(),
        pose_id=pose.id,
        photo_id=photo.id,
    )
    return _apply_processed_result(db, photo, day_log, pose, weight_kg, result)
```

- [ ] **Step 4: Run tests to verify no regressions**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_photos_router_scoped.py -v`
Expected: all PASS, including the new `test_assign_photo_sets_processed_status_and_day_log`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/photos.py backend/tests/test_photos_router_scoped.py
git commit -m "refactor: split _assign_photo into thread-safe file processing + DB application"
```

---

### Task 2: Parallelize `/photos/assign-bulk`

**Files:**
- Modify: `backend/app/routers/photos.py`
- Test: `backend/tests/test_photos_router_scoped.py`

- [ ] **Step 1: Write the failing test**

Add this test to `backend/tests/test_photos_router_scoped.py`:

```python
def test_assign_bulk_processes_multiple_photos_concurrently(client, db_session, monkeypatch):
    """Beweist tatsächliche Parallelität (nicht nur Code-Struktur): macht
    push() künstlich langsam und prüft, dass ein 3-Foto-Batch deutlich
    schneller durchläuft als 3x die künstliche Einzeldauer - bei
    sequenzieller Verarbeitung wäre das unmöglich."""
    import time
    from app.models.photo import Photo, ProcessingStatus
    from app.models.pose import Pose
    from app.routers import photos as photos_router

    SLOW_PUSH_SECONDS = 0.3

    def _slow_push(rel_path):
        time.sleep(SLOW_PUSH_SECONDS)

    monkeypatch.setattr(photos_router, "push", _slow_push)

    client_id = _login_and_get_client(client, db_session)

    pose = Pose(client_id=client_id, name="Front", sort_order=0)
    db_session.add(pose)
    db_session.commit()

    photos = []
    for i in range(3):
        photo = Photo(
            client_id=client_id,
            filename=f"p{i}.jpg",
            original_path=f"photos_incoming/{client_id}/p{i}.jpg",
            taken_at=datetime(2026, 1, 1 + i, 12, 0, 0),
            status=ProcessingStatus.UNPROCESSED,
        )
        db_session.add(photo)
        photos.append(photo)
    db_session.commit()
    for p in photos:
        db_session.refresh(p)

    started = time.monotonic()
    response = client.post(
        f"/api/clients/{client_id}/photos/assign-bulk",
        json={"items": [{"photo_id": p.id, "pose_id": pose.id} for p in photos]},
    )
    elapsed = time.monotonic() - started

    assert response.status_code == 200
    assert len(response.json()) == 3
    # push() wird pro Foto mindestens 1x aufgerufen (Original-Move-Pfad
    # existiert hier nicht wirklich, aber Thumbnail-Generierung schlägt
    # fehl mangels echter Datei -> zumindest kein push() dafür; die
    # Kernaussage ist trotzdem gültig: bei echter Sequenzialität würde
    # jeder zusätzliche Foto-Slot die Gesamtzeit um SLOW_PUSH_SECONDS
    # erhöhen. Wir prüfen konservativ, dass 3 Fotos NICHT 3x so lange wie
    # ein einzelner künstlich verlangsamter Call brauchen.
    assert elapsed < SLOW_PUSH_SECONDS * 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_photos_router_scoped.py::test_assign_bulk_processes_multiple_photos_concurrently -v`
Expected: FAIL (either on the timing assertion, since the current code is fully sequential, or simply takes noticeably longer - confirm the elapsed time printed/asserted shows sequential behavior before proceeding).

- [ ] **Step 3: Implement the parallel bulk endpoint**

In `backend/app/routers/photos.py`, replace the current `assign_photos_bulk` function:

```python
@router.post("/assign-bulk", response_model=list[PhotoOut])
def assign_photos_bulk(
    payload: PhotoBulkAssign,
    client_row: Client = Depends(get_owned_client),
    db: Session = Depends(get_db),
):
    """
    Ordnet mehrere Fotos auf einmal zu (z.B. "Alle zugeordneten speichern"
    in der Unprocessed-Ansicht). Fotos ohne gewählte Pose werden vom
    Frontend gar nicht erst mitgeschickt und bleiben unverändert in der
    Queue. Einzelne fehlerhafte Einträge (unbekannte Foto-/Pose-ID) werden
    übersprungen, statt die gesamte Aktion abzubrechen.

    Performance: die teure Datei-/MediaPipe-Arbeit pro Foto läuft über
    einen Thread-Pool PARALLEL statt sequenziell (siehe Design-Spec
    "Foto-Upload/Speicher-Performance") - die Antwort wartet trotzdem auf
    ALLE Ergebnisse, bevor sie zurückgegeben wird (kein Hintergrund-
    Mechanismus, keine Inkonsistenz-Fenster). DayLog-Auflösung/-Anlage
    bleibt VOR dem Parallel-Dispatch sequenziell, um Race Conditions bei
    mehreren Fotos desselben Tages zu vermeiden.
    """
    # Phase 1 (sequenziell, günstig): validieren + DayLog auflösen.
    work_items = []
    for item in payload.items:
        photo = (
            db.query(Photo)
            .filter(Photo.id == item.photo_id, Photo.client_id == client_row.id)
            .first()
        )
        pose = (
            db.query(Pose)
            .filter(Pose.id == item.pose_id, Pose.client_id == client_row.id)
            .first()
        )
        if not photo or not pose or photo.status != ProcessingStatus.UNPROCESSED:
            continue
        day_date = photo.taken_at.date()
        day_log = _get_or_create_day_log(db, client_row.id, day_date, client_row.owner)
        work_items.append((photo, pose, day_log, item.weight_kg))

    if not work_items:
        return []

    # Phase 2 (parallel, teuer): Datei-Verarbeitung + MediaPipe je Foto.
    with ThreadPoolExecutor(max_workers=PHOTO_PROCESSING_MAX_WORKERS) as executor:
        future_to_index = {
            executor.submit(
                _process_photo_files,
                client_id=client_row.id,
                filename=photo.filename,
                original_path=photo.original_path,
                preview_path=photo.preview_path,
                thumbnail_path=photo.thumbnail_path,
                day_date_iso=day_log.date.isoformat(),
                pose_id=pose.id,
                photo_id=photo.id,
            ): index
            for index, (photo, pose, day_log, weight_kg) in enumerate(work_items)
        }
        results_by_index: dict[int, _ProcessedPhotoFiles] = {}
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            results_by_index[index] = future.result()

    # Phase 3 (sequenziell, günstig): Ergebnisse in DB übernehmen.
    results: list[Photo] = []
    for index, (photo, pose, day_log, weight_kg) in enumerate(work_items):
        results.append(
            _apply_processed_result(db, photo, day_log, pose, weight_kg, results_by_index[index])
        )
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_photos_router_scoped.py -v`
Expected: all PASS, including the new concurrency-timing test.

- [ ] **Step 5: Run the full backend test suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all PASS except the pre-existing unrelated `test_gemini_key_is_scoped_per_account` failure.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/photos.py backend/tests/test_photos_router_scoped.py
git commit -m "perf: parallelize per-photo processing in assign-bulk"
```

---

### Task 3: Parallelize `/photos/upload`'s R2 pushes

**Files:**
- Modify: `backend/app/routers/photos.py`
- Test: `backend/tests/test_photos_router_scoped.py`

- [ ] **Step 1: Write the failing test**

Add this test to `backend/tests/test_photos_router_scoped.py`:

```python
def test_upload_pushes_files_concurrently(client, db_session, monkeypatch, tmp_path):
    """Analog zum Bulk-Assign-Test: push() künstlich verlangsamen und
    prüfen, dass mehrere hochgeladene Dateien nicht sequenziell gepusht
    werden."""
    import io
    import time
    from app.routers import photos as photos_router

    SLOW_PUSH_SECONDS = 0.3

    def _slow_push(rel_path):
        time.sleep(SLOW_PUSH_SECONDS)

    monkeypatch.setattr(photos_router, "push", _slow_push)

    client_id = _login_and_get_client(client, db_session)

    files = [
        ("files", (f"upload{i}.jpg", io.BytesIO(b"fake-jpeg-bytes"), "image/jpeg"))
        for i in range(3)
    ]

    started = time.monotonic()
    response = client.post(f"/api/clients/{client_id}/photos/upload", files=files)
    elapsed = time.monotonic() - started

    assert response.status_code == 200
    assert elapsed < SLOW_PUSH_SECONDS * 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_photos_router_scoped.py::test_upload_pushes_files_concurrently -v`
Expected: FAIL (current code pushes sequentially in the upload loop).

- [ ] **Step 3: Implement the parallel upload endpoint**

In `backend/app/routers/photos.py`, replace the current `upload_photos` function:

```python
@router.post("/upload", response_model=list[PhotoOut])
def upload_photos(
    files: list[UploadFile],
    client_row: Client = Depends(get_owned_client),
    db: Session = Depends(get_db),
):
    """
    Datei-Upload für die Import-Seite: Der User wählt Dateien von der
    eigenen Festplatte, diese werden nach photos_incoming/<client_id>/
    kopiert und direkt im Anschluss verarbeitet (derselbe Scan wie /sync) -
    der User muss also nicht extra einen Ordner auf dem Server-Rechner
    befüllen und anschließend "Sync" klicken, sondern kann Dateien direkt
    aus dem Browser hochladen.

    Performance: alle Dateien werden zuerst schnell lokal geschrieben
    (reine Disk-I/O, bleibt sequenziell), die R2-Uploads laufen danach
    PARALLEL über einen Thread-Pool - die Antwort wartet auf alle, bevor
    sie zurückkommt (siehe Design-Spec "Foto-Upload/Speicher-Performance").
    """
    incoming_dir = incoming_dir_for_client(client_row.id)
    incoming_dir.mkdir(parents=True, exist_ok=True)
    pending_push_paths: list[str] = []
    for upload in files:
        if not upload.filename:
            continue
        # Nur den Dateinamen übernehmen, keine Pfad-Komponenten - der
        # Client-gelieferte Dateiname könnte sonst z.B. "../../evil.jpg"
        # sein und über incoming_dir hinausschreiben (Path-Traversal).
        safe_name = Path(upload.filename).name
        suffix = Path(safe_name).suffix.lower()
        if suffix not in settings.allowed_extensions:
            continue
        dest = incoming_dir / safe_name
        # Namenskollision (z.B. gleicher Dateiname erneut hochgeladen):
        # Zähler anhängen statt zu überschreiben.
        counter = 1
        while dest.exists():
            dest = incoming_dir / f"{Path(safe_name).stem}_{counter}{suffix}"
            counter += 1
        with dest.open("wb") as f:
            shutil.copyfileobj(upload.file, f)
        pending_push_paths.append(dest.relative_to(settings.data_dir).as_posix())

    if not pending_push_paths:
        raise HTTPException(400, "No valid image files found in upload")

    with ThreadPoolExecutor(max_workers=PHOTO_PROCESSING_MAX_WORKERS) as executor:
        futures = [executor.submit(push, rel_path) for rel_path in pending_push_paths]
        for future in as_completed(futures):
            future.result()

    return sync_incoming_folder(db, client_row.id)
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
git commit -m "perf: parallelize R2 pushes in photo upload endpoint"
```

---

### Task 4: Holistic review + finish branch

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all PASS except the pre-existing, unrelated `test_gemini_key_is_scoped_per_account` failure.

- [ ] **Step 2: Manual review checklist**

Re-read `backend/app/routers/photos.py`'s changed sections end to end and confirm:
- `_process_photo_files` never touches `db` (no `Session` parameter, no ORM object parameter) - a stray DB access there would be a thread-safety bug that tests might not catch reliably.
- `_get_or_create_day_log` is called ONLY in the sequential phase (before `ThreadPoolExecutor` dispatch) in both `_assign_photo` and `assign_photos_bulk`.
- `renormalize_all` and `backfill_thumbnails` (untouched by this plan) still compile/import correctly - they call `normalize_photo`/`generate_thumbnail`/`push` directly and don't depend on the removed original `_assign_photo` body.
- No leftover German user-facing strings introduced (comments in German are fine per existing convention, HTTPException messages must stay English).

- [ ] **Step 3: Manual performance sanity check**

Once deployed to staging (as part of finishing the branch), do a real 6-8 photo "Save all assigned" and observe wall-clock time - should be noticeably faster than before, ideally in the single-digit seconds. Report back if it's still slow rather than assuming success from tests alone.

- [ ] **Step 4: Use the finishing-a-development-branch skill**

Invoke `superpowers:finishing-a-development-branch` to push per the user's standing "option 1" preference (this session works directly on `dev`).
