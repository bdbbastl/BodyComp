from datetime import datetime, timezone

from app.models.checkin_submission import CheckinStatus, CheckinSubmission
from app.models.user import User
from app.services.auth import hash_password


def _login(client, db_session, email="a@b.com", password="pw12345"):
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name="A",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.commit()
    client.post("/api/auth/login", json={"email": email, "password": password})
    return user


def test_get_checkin_page_by_valid_token(client, db_session):
    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    token = created["checkin_token"]

    response = client.get(f"/api/public/checkin/{token}")
    assert response.status_code == 200
    body = response.json()
    assert body["client_name"] == "Max"
    assert body["submissions"] == []


def test_get_checkin_page_includes_submission_history(client, db_session):
    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    token = created["checkin_token"]

    submission = CheckinSubmission(
        client_id=created["id"],
        weight_kg=82.5,
        client_note="Fühle mich gut",
        status=CheckinStatus.REVIEWED,
        coach_feedback_text="Weiter so!",
        coach_feedback_video_url="https://loom.com/share/abc",
    )
    db_session.add(submission)
    db_session.commit()

    response = client.get(f"/api/public/checkin/{token}")
    body = response.json()
    assert len(body["submissions"]) == 1
    assert body["submissions"][0]["weight_kg"] == 82.5
    assert body["submissions"][0]["coach_feedback_text"] == "Weiter so!"


def test_get_checkin_page_with_invalid_token_returns_404(client, db_session):
    response = client.get("/api/public/checkin/does-not-exist")
    assert response.status_code == 404


def test_submit_checkin_sanitizes_path_traversal_filename(client, db_session):
    """Ein Dateiname wie "../../evil.jpg" darf niemals außerhalb von
    data_dir landen - siehe Sicherheits-Fix nach Code-Review von Task 5
    (dieser Endpunkt ist unauthentifiziert). Nur der reine Dateiname
    ("evil.jpg") darf übrig bleiben, verarbeitet landet er in
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

    # Nirgendwo außerhalb von data_dir darf eine Datei namens evil.jpg
    # entstanden sein.
    for candidate in settings.data_dir.parent.glob("evil.jpg"):
        assert False, f"Path-Traversal: Datei außerhalb data_dir geschrieben: {candidate}"


def test_get_checkin_page_includes_client_poses(client, db_session):
    from app.models.pose import Pose

    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    token = created["checkin_token"]

    # Client-Anlage seedet bereits Standard-Posen (seed_default_poses_for_client)
    # - hier zusätzlich eine eigene Pose anlegen und prüfen, dass sie mit
    # dabei ist, statt eine exakte Gesamtliste zu erwarten.
    pose = Pose(client_id=created["id"], name="Custom Pose XYZ", sort_order=99)
    db_session.add(pose)
    db_session.commit()
    db_session.refresh(pose)

    response = client.get(f"/api/public/checkin/{token}")
    body = response.json()
    assert {"id": pose.id, "name": "Custom Pose XYZ"} in body["poses"]


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


def test_submit_checkin_blocked_for_single_account_after_free_quota(client, db_session, monkeypatch):
    """Regression: der Magic-Link-Check-in muss dasselbe kumulative
    Freikontingent respektieren wie day_logs.py/photos.py - sonst wäre
    er eine Umgehung der Paywall (gefunden im finalen Billing-Review).
    Jede Einreichung braucht ein ANDERES Datum, da mehrere Einreichungen
    am selben Tag denselben DayLog nur aktualisieren (kein neuer
    Check-in fürs Kontingent, siehe Task 5)."""
    import datetime as datetime_module

    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Ich"}).json()
    token = created["checkin_token"]

    for day, expected_status in ((1, 201), (2, 201), (3, 402)):
        class _FixedDate(datetime_module.date):
            @classmethod
            def today(cls):
                return datetime_module.date(2026, 1, day)

        monkeypatch.setattr("app.routers.public_checkin.date_", _FixedDate)
        response = client.post(f"/api/public/checkin/{token}/submit", data={"weight_kg": "80"})
        assert response.status_code == expected_status, f"Tag {day}: erwartet {expected_status}, bekam {response.status_code}"


def test_submit_checkin_with_weight_and_note_creates_pending_submission(client, db_session):
    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    token = created["checkin_token"]

    response = client.post(
        f"/api/public/checkin/{token}/submit",
        data={"weight_kg": "81.2", "client_note": "Diese Woche war hart"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["weight_kg"] == 81.2
    assert body["client_note"] == "Diese Woche war hart"


def test_submit_checkin_writes_weight_into_today_daylog(client, db_session):
    from datetime import date

    from app.models.day_log import DayLog

    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    token = created["checkin_token"]

    client.post(f"/api/public/checkin/{token}/submit", data={"weight_kg": "81.2"})

    day_log = (
        db_session.query(DayLog)
        .filter(DayLog.client_id == created["id"], DayLog.date == date.today())
        .first()
    )
    assert day_log is not None
    assert day_log.weight_kg == 81.2


def test_submit_checkin_with_invalid_token_returns_404(client, db_session):
    response = client.post("/api/public/checkin/does-not-exist/submit", data={"weight_kg": "80"})
    assert response.status_code == 404


def test_submit_checkin_accepts_comma_decimal_weight(client, db_session):
    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    token = created["checkin_token"]

    response = client.post(
        f"/api/public/checkin/{token}/submit",
        data={"weight_kg": "76,05"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["weight_kg"] == 76.05


def test_submit_checkin_does_not_attribute_unrelated_incoming_photo(client, db_session, monkeypatch, tmp_path):
    """Regression: sync_incoming_folder scannt den GESAMTEN incoming_dir,
    nicht nur die Dateien dieses Requests - eine Datei, die der Coach
    manuell (oder ein vorheriger, noch nicht synchronisierter Prozess)
    dort abgelegt hat, darf NICHT dieser Einreichung zugeordnet werden
    (gefunden im finalen Holistic-Review)."""
    from app.core.config import settings
    from app.models.photo import Photo
    from app.models.pose import Pose
    from app.services.storage_paths import incoming_dir_for_client

    # Isoliert von backend/data/ - ohne das würden wiederholte Testläufe
    # Dateinamen-Kollisionen mit Resten vorheriger Läufe provozieren
    # (gefunden live: "client_upload_3.jpg" statt "client_upload.jpg").
    monkeypatch.setattr(settings, "data_dir", tmp_path)

    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    token = created["checkin_token"]
    pose = Pose(client_id=created["id"], name="Front", sort_order=0)
    db_session.add(pose)
    db_session.commit()
    db_session.refresh(pose)

    # Simuliert eine bereits im incoming_dir liegende, noch nicht
    # synchronisierte Datei, wie sie z.B. beim manuellen Server-seitigen
    # Ordner-Workflow entstehen kann (siehe folder_sync.py-Docstring).
    incoming_dir = incoming_dir_for_client(created["id"])
    incoming_dir.mkdir(parents=True, exist_ok=True)
    (incoming_dir / "coach_dropped_this.jpg").write_bytes(b"pre-existing-file")

    response = client.post(
        f"/api/public/checkin/{token}/submit",
        data={"weight_kg": "80", "pose_ids": str(pose.id)},
        files={"files": ("client_upload.jpg", b"client-photo-bytes", "image/jpeg")},
    )
    assert response.status_code == 201
    body = response.json()

    submitted_filenames = {p["filename"] for p in body["photos"]}
    assert submitted_filenames == {"client_upload.jpg"}

    # Die vorbestehende Datei wurde zwar synchronisiert (existiert jetzt
    # als Photo-Row), aber NICHT dieser Submission zugeordnet.
    pre_existing_photo = (
        db_session.query(Photo).filter(Photo.filename == "coach_dropped_this.jpg").first()
    )
    assert pre_existing_photo is not None
    assert pre_existing_photo.checkin_submission_id is None


def test_submit_checkin_rejects_too_many_files(client, db_session):
    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    token = created["checkin_token"]

    files = [
        ("files", (f"photo{i}.jpg", b"bytes", "image/jpeg")) for i in range(11)
    ]
    response = client.post(f"/api/public/checkin/{token}/submit", files=files)
    assert response.status_code == 400


def test_submit_checkin_sends_notification_email_to_coach(client, db_session, monkeypatch):
    sent = {}

    def fake_send(*, to, client_name, checkins_url):
        sent["to"] = to
        sent["client_name"] = client_name

    monkeypatch.setattr(
        "app.routers.public_checkin.send_checkin_submitted_email", fake_send
    )

    _login(client, db_session, email="coach@example.com")
    created = client.post("/api/clients", json={"name": "Max"}).json()
    token = created["checkin_token"]

    client.post(f"/api/public/checkin/{token}/submit", data={"weight_kg": "81.2"})

    assert sent["to"] == "coach@example.com"
    assert sent["client_name"] == "Max"
