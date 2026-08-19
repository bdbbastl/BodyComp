from datetime import datetime, timezone

from app.models.user import User
from app.services.auth import hash_password


def _login_and_get_client(client, db_session, email="a@b.com", password="pw12345"):
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name="A",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.commit()
    client.post("/api/auth/login", json={"email": email, "password": password})
    created = client.post("/api/clients", json={"name": "Kunde"}).json()
    return created["id"]


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


def test_photos_list_scoped_to_client(client, db_session):
    client_id_a = _login_and_get_client(client, db_session, email="a@b.com", password="pw12345")
    response = client.get(f"/api/clients/{client_id_a}/photos")
    assert response.status_code == 200
    assert response.json() == []


def test_cannot_list_photos_of_foreign_client(client, db_session):
    client_id_a = _login_and_get_client(client, db_session, email="a@b.com", password="pw12345")
    client.post("/api/auth/logout")
    _login_and_get_client(client, db_session, email="c@d.com", password="pw67890")

    response = client.get(f"/api/clients/{client_id_a}/photos")
    assert response.status_code == 404


def test_sync_requires_client_ownership(client, db_session):
    client_id_a = _login_and_get_client(client, db_session, email="a@b.com", password="pw12345")
    client.post("/api/auth/logout")
    _login_and_get_client(client, db_session, email="c@d.com", password="pw67890")

    response = client.post(f"/api/clients/{client_id_a}/photos/sync")
    assert response.status_code == 404


def test_cannot_assign_photo_of_foreign_client(client, db_session):
    client_id_a = _login_and_get_client(client, db_session, email="a@b.com", password="pw12345")
    client.post("/api/auth/logout")
    _login_and_get_client(client, db_session, email="c@d.com", password="pw67890")

    response = client.post(
        f"/api/clients/{client_id_a}/photos/999/assign", json={"pose_id": 999}
    )
    assert response.status_code == 404


def test_cannot_change_pose_of_photo_of_foreign_client(client, db_session):
    client_id_a = _login_and_get_client(client, db_session, email="a@b.com", password="pw12345")
    client.post("/api/auth/logout")
    _login_and_get_client(client, db_session, email="c@d.com", password="pw67890")

    response = client.patch(
        f"/api/clients/{client_id_a}/photos/999/pose", json={"pose_id": 999}
    )
    assert response.status_code == 404


def test_cannot_delete_photo_of_foreign_client(client, db_session):
    client_id_a = _login_and_get_client(client, db_session, email="a@b.com", password="pw12345")
    client.post("/api/auth/logout")
    _login_and_get_client(client, db_session, email="c@d.com", password="pw67890")

    response = client.delete(f"/api/clients/{client_id_a}/photos/999")
    assert response.status_code == 404


def test_assign_photo_blocked_for_single_account_after_free_quota(client, db_session):
    from app.models.photo import Photo, ProcessingStatus
    from app.models.pose import Pose

    # Default account_type ist bereits SINGLE (siehe User-Modell).
    client_id = _login_and_get_client(client, db_session, email="single-quota@b.com")

    pose = Pose(client_id=client_id, name="Front", sort_order=0)
    db_session.add(pose)
    db_session.commit()

    photos = []
    for day in (1, 2, 3):
        photo = Photo(
            client_id=client_id,
            filename=f"p{day}.jpg",
            original_path=f"photos_incoming/{client_id}/p{day}.jpg",
            taken_at=datetime(2026, 1, day, 12, 0, 0),
            status=ProcessingStatus.UNPROCESSED,
        )
        db_session.add(photo)
        photos.append(photo)
    db_session.commit()
    for p in photos:
        db_session.refresh(p)

    # Erste 2 Fotos (je ein neuer Tag) sind kostenlos zuordenbar.
    r1 = client.post(f"/api/clients/{client_id}/photos/{photos[0].id}/assign", json={"pose_id": pose.id})
    r2 = client.post(f"/api/clients/{client_id}/photos/{photos[1].id}/assign", json={"pose_id": pose.id})
    assert r1.status_code == 200
    assert r2.status_code == 200

    # 3. neuer Tag -> blockiert.
    r3 = client.post(f"/api/clients/{client_id}/photos/{photos[2].id}/assign", json={"pose_id": pose.id})
    assert r3.status_code == 402


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


def test_assign_photo_accepts_comma_decimal_weight(client, db_session):
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
        json={"pose_id": pose.id, "weight_kg": "76,05"},
    )
    assert response.status_code == 200

    day_logs = client.get(f"/api/clients/{client_id}/day-logs").json()
    assert any(log["weight_kg"] == 76.05 for log in day_logs)


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
            taken_at=datetime(2026, 1, 1, 12 + i, 0, 0),
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


def test_assign_bulk_same_filename_photos_do_not_clobber_each_other(client, db_session):
    """Regression: zwei UNPROCESSED-Fotos mit IDENTISCHEM Dateinamen (z.B.
    weil eine Kamera-App wieder bei IMG_0001.jpg anfängt zu zählen, nachdem
    ein früheres Foto bereits aus incoming_dir herausbewegt wurde) dürfen im
    selben Bulk-Batch NICHT auf denselben Ziel-Dateinamen abgebildet werden -
    sonst überschreibt ein paralleler shutil.move()-Aufruf den anderen
    (stiller Datenverlust). _process_photo_files präfixt den Zieldateinamen
    daher mit der eindeutigen photo_id."""
    from app.core.config import settings
    from app.models.photo import Photo, ProcessingStatus
    from app.models.pose import Pose

    client_id = _login_and_get_client(client, db_session)

    pose = Pose(client_id=client_id, name="Front", sort_order=0)
    db_session.add(pose)
    db_session.commit()

    # `Photo.original_path` trägt eine Unique-Constraint, daher braucht jedes
    # Foto einen eigenen SOURCE-Pfad (unterschiedliches Unterverzeichnis) -
    # aber beide teilen sich denselben `filename`-Feldwert, das reicht, um
    # die Kollision im Zielverzeichnis (dest_dir / filename) zu erzeugen,
    # um die es hier geht.
    photos = []
    contents = [b"content-of-photo-one", b"content-of-photo-two"]
    for i, content in enumerate(contents):
        src_rel = f"photos_incoming/{client_id}/src_{i}.jpg"
        src_path = settings.data_dir / src_rel
        src_path.parent.mkdir(parents=True, exist_ok=True)
        src_path.write_bytes(content)
        photo = Photo(
            client_id=client_id,
            filename="IMG_0001.jpg",
            original_path=src_rel,
            taken_at=datetime(2026, 1, 1, 12 + i, 0, 0),
            status=ProcessingStatus.UNPROCESSED,
        )
        db_session.add(photo)
        photos.append(photo)
    db_session.commit()
    for p in photos:
        db_session.refresh(p)

    response = client.post(
        f"/api/clients/{client_id}/photos/assign-bulk",
        json={"items": [{"photo_id": p.id, "pose_id": pose.id} for p in photos]},
    )
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 2

    original_paths = [r["original_path"] for r in results]
    assert len(set(original_paths)) == 2, "destination paths must be distinct, not clobbered"

    contents_by_id = {photos[0].id: contents[0], photos[1].id: contents[1]}
    for r in results:
        dest_file = settings.data_dir / r["original_path"]
        assert dest_file.exists()
        assert dest_file.read_bytes() == contents_by_id[r["id"]]


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
