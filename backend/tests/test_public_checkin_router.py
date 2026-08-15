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
    incoming_dir landen - siehe Sicherheits-Fix nach Code-Review von
    Task 5 (dieser Endpunkt ist unauthentifiziert). Nur der reine
    Dateiname ("evil.jpg") darf übrig bleiben, innerhalb von incoming_dir."""
    from app.core.config import settings
    from app.services.storage_paths import incoming_dir_for_client

    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    token = created["checkin_token"]

    malicious_name = "../../../../evil.jpg"
    response = client.post(
        f"/api/public/checkin/{token}/submit",
        files={"files": (malicious_name, b"fake-image-bytes", "image/jpeg")},
    )
    assert response.status_code == 201

    # Nirgendwo außerhalb von data_dir darf eine Datei namens evil.jpg
    # entstanden sein.
    for candidate in settings.data_dir.parent.glob("evil.jpg"):
        assert False, f"Path-Traversal: Datei außerhalb data_dir geschrieben: {candidate}"

    # Der sanitierte Dateiname landet stattdessen sicher innerhalb von
    # incoming_dir für diesen Client.
    incoming_dir = incoming_dir_for_client(created["id"])
    assert (incoming_dir / "evil.jpg").exists()


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


def test_submit_checkin_does_not_attribute_unrelated_incoming_photo(client, db_session):
    """Regression: sync_incoming_folder scannt den GESAMTEN incoming_dir,
    nicht nur die Dateien dieses Requests - eine Datei, die der Coach
    manuell (oder ein vorheriger, noch nicht synchronisierter Prozess)
    dort abgelegt hat, darf NICHT dieser Einreichung zugeordnet werden
    (gefunden im finalen Holistic-Review)."""
    from app.models.photo import Photo
    from app.services.storage_paths import incoming_dir_for_client

    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    token = created["checkin_token"]

    # Simuliert eine bereits im incoming_dir liegende, noch nicht
    # synchronisierte Datei, wie sie z.B. beim manuellen Server-seitigen
    # Ordner-Workflow entstehen kann (siehe folder_sync.py-Docstring).
    incoming_dir = incoming_dir_for_client(created["id"])
    incoming_dir.mkdir(parents=True, exist_ok=True)
    (incoming_dir / "coach_dropped_this.jpg").write_bytes(b"pre-existing-file")

    response = client.post(
        f"/api/public/checkin/{token}/submit",
        data={"weight_kg": "80"},
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
