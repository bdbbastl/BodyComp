# Check-in-Einreichung & Review-Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Klienten können über einen dauerhaften, passwortlosen Magic-Link (`/checkin/{token}`) eigene Check-ins (Gewicht/Notiz/Fotos) einreichen. Der Coach bekommt eine Review-Queue (Dashboard-Badge + eigener "Check-ins"-Tab pro Klient), kann kurzes Freitext-Feedback und einen Video-Link (Loom o.ä.) hinterlassen und Check-ins als geprüft markieren. Zusätzlich: Compliance-Anzeige, private Coach-Notiz pro Klient, und automatische E-Mails (Coach bei neuer Einreichung, Klient bei Inaktivität).

**Architecture:** Neues, schlankes `CheckinSubmission`-Modell als Review-Schicht oberhalb der bestehenden `DayLog`/`Photo`-Tabellen (siehe Design-Spec). Magic-Link-Auth über einen opaken, zufälligen Token direkt auf `Client` (kein Ablauf, vom Coach neu generierbar) statt eines vollen Klienten-Logins. Ein neuer öffentlicher Router prüft den Token statt der Session-Cookie-Auth. Erinnerungsmails laufen über einen In-Process-APScheduler-Job.

**Tech Stack:** FastAPI/SQLAlchemy (Backend), React/TypeScript/React-Router (Frontend), Resend (E-Mail), APScheduler (Erinnerungs-Job, neue Dependency).

---

## Part 1 — Backend: Datenmodell

### Task 1: `Client`-Erweiterungen (Magic-Link-Token, Coach-Notiz, E-Mail, Erinnerungs-Konfiguration)

**Files:**
- Modify: `backend/app/models/client.py`
- Modify: `backend/app/core/migrations.py`
- Test: `backend/tests/test_clients_router.py`

- [ ] **Step 1: Failing test**

Append to `backend/tests/test_clients_router.py`:

```python
def test_new_client_gets_a_checkin_token(client, db_session):
    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    assert created["checkin_token"]
    assert len(created["checkin_token"]) >= 20


def test_client_update_can_set_coach_private_note_email_and_reminder_days(client, db_session):
    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    updated = client.patch(
        f"/api/clients/{created['id']}",
        json={
            "coach_private_note": "Knieprobleme, langsam steigern",
            "email": "max@example.com",
            "checkin_reminder_days": 3,
        },
    ).json()
    assert updated["coach_private_note"] == "Knieprobleme, langsam steigern"
    assert updated["email"] == "max@example.com"
    assert updated["checkin_reminder_days"] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_clients_router.py -k checkin_token -v`
Expected: FAIL (`KeyError: 'checkin_token'` bzw. Feld existiert nicht in der Response).

- [ ] **Step 3: `Client`-Modell erweitern**

In `backend/app/models/client.py`, Import ergänzen und neue Spalten hinzufügen:

```python
import secrets
from datetime import date as date_, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    birth_date: Mapped[date_ | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(50), nullable=True)
    start_date: Mapped[date_ | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    # Magic-Link-Zugang für Klienten-Check-in-Einreichung (kein Login, kein
    # Ablauf) - siehe Design-Spec Abschnitt "Magic-Link-Mechanismus". Der
    # Coach kann den Token im Klientenprofil jederzeit neu generieren, was
    # den alten Link sofort ungültig macht.
    checkin_token: Mapped[str] = mapped_column(
        String(64), default=lambda: secrets.token_urlsafe(24), nullable=False
    )
    # Rein intern, NIE im Klienten-Flow sichtbar - siehe Design-Spec.
    coach_private_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Voraussetzung für Erinnerungsmails (siehe services/checkin_reminders.py).
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # None = keine automatische Erinnerung für diesen Klienten.
    checkin_reminder_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    owner: Mapped["User"] = relationship(back_populates="clients")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Client id={self.id} name={self.name!r} owner_id={self.owner_id}>"
```

- [ ] **Step 4: Lightweight-Migration + Backfill für bestehende Clients**

In `backend/app/core/migrations.py`: Import `secrets` ergänzen, neue Spalten in `_PENDING_COLUMNS` eintragen, und einen Backfill-Block für `checkin_token` ergänzen (analog zum bestehenden `email_verified_at`-Backfill):

```python
import secrets

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

_PENDING_COLUMNS: list[tuple[str, str, str]] = [
    ("photos", "preview_path", "VARCHAR(1000)"),
    ("photos", "thumbnail_path", "VARCHAR(1000)"),
    ("photos", "client_id", "INTEGER"),
    ("poses", "client_id", "INTEGER"),
    ("day_logs", "client_id", "INTEGER"),
    ("clients", "birth_date", "DATE"),
    ("users", "google_id", "VARCHAR(255)"),
    ("users", "email_verified_at", "DATETIME"),
    ("users", "privacy_accepted_at", "DATETIME"),
    ("users", "sessions_invalidated_at", "DATETIME"),
    ("clients", "checkin_token", "VARCHAR(64)"),
    ("clients", "coach_private_note", "TEXT"),
    ("clients", "email", "VARCHAR(255)"),
    ("clients", "checkin_reminder_days", "INTEGER"),
    ("clients", "last_reminder_sent_at", "DATETIME"),
    ("photos", "checkin_submission_id", "INTEGER"),
]


def run_lightweight_migrations(engine: Engine) -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, column, sql_type in _PENDING_COLUMNS:
            if table not in existing_tables:
                continue
            existing_columns = {col["name"] for col in inspector.get_columns(table)}
            if column in existing_columns:
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))

        if "users" in existing_tables:
            existing_user_columns = {col["name"] for col in inspector.get_columns("users")}
            if "email_verified_at" in existing_user_columns:
                conn.execute(text(
                    "UPDATE users SET email_verified_at = created_at "
                    "WHERE email_verified_at IS NULL AND password_hash IS NOT NULL"
                ))

        if "clients" in existing_tables:
            existing_client_columns = {col["name"] for col in inspector.get_columns("clients")}
            if "checkin_token" in existing_client_columns:
                rows_needing_token = conn.execute(
                    text("SELECT id FROM clients WHERE checkin_token IS NULL")
                ).fetchall()
                for (client_id,) in rows_needing_token:
                    conn.execute(
                        text("UPDATE clients SET checkin_token = :token WHERE id = :id"),
                        {"token": secrets.token_urlsafe(24), "id": client_id},
                    )
```

- [ ] **Step 5: `ClientCreate`/`ClientUpdate`/`ClientOut`-Schemas erweitern**

In `backend/app/schemas/client.py`:

```python
from datetime import date as date_, datetime

from pydantic import BaseModel, Field


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    height_cm: float | None = None
    birth_date: date_ | None = None
    gender: str | None = None
    start_date: date_ | None = None


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    height_cm: float | None = None
    birth_date: date_ | None = None
    gender: str | None = None
    start_date: date_ | None = None
    coach_private_note: str | None = None
    email: str | None = None
    checkin_reminder_days: int | None = None


class ClientOut(BaseModel):
    id: int
    name: str
    height_cm: float | None
    birth_date: date_ | None
    gender: str | None
    start_date: date_ | None
    created_at: datetime
    photo_count: int
    last_activity: date_ | None
    pending_checkins_count: int
    checkin_token: str
    coach_private_note: str | None
    email: str | None
    checkin_reminder_days: int | None

    class Config:
        from_attributes = True
```

- [ ] **Step 6: Router anpassen (`_client_row_to_out` + `update_client`)**

In `backend/app/routers/clients.py`: `_client_row_to_out` bekommt die neuen Felder inkl. `pending_checkins_count` (vorerst hartcodiert `0` - wird in Task 8 durch die echte Aggregation ersetzt, damit dieser Task für sich lauffähig bleibt):

```python
def _client_row_to_out(client_row: Client, photo_count: int, last_activity_dt, pending_checkins_count: int = 0) -> ClientOut:
    return ClientOut(
        id=client_row.id,
        name=client_row.name,
        height_cm=client_row.height_cm,
        birth_date=client_row.birth_date,
        gender=client_row.gender,
        start_date=client_row.start_date,
        created_at=client_row.created_at,
        photo_count=photo_count,
        last_activity=last_activity_dt.date() if last_activity_dt else None,
        pending_checkins_count=pending_checkins_count,
        checkin_token=client_row.checkin_token,
        coach_private_note=client_row.coach_private_note,
        email=client_row.email,
        checkin_reminder_days=client_row.checkin_reminder_days,
    )
```

Alle Aufrufer von `_client_row_to_out` (in `list_clients`, `_to_client_out`) bleiben sonst unverändert - sie übergeben einfach kein `pending_checkins_count` mit (Default `0`).

`update_client` muss die neuen Felder mitschreiben - das passiert bereits automatisch, da die Funktion generisch über `payload.model_dump(exclude_unset=True).items()` iteriert (keine Änderung am Router-Code nötig, nur am Schema aus Step 5).

- [ ] **Step 7: Tests laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_clients_router.py -v`
Expected: alle PASS, inkl. der beiden neuen Tests.

- [ ] **Step 8: Selbst-Review**

Prüfe: legt `POST /api/clients` wirklich für JEDEN neuen Client automatisch einen `checkin_token` an (auch den impliziten Client aus `services/account.py create_account`, der `Client(owner_id=user.id, name=display_name)` ohne explizite Felder anlegt)? Ja - der Python-seitige `default=lambda: secrets.token_urlsafe(24)` auf dem Modell greift bei JEDER `Client(...)`-Instanziierung ohne explizit gesetzten Wert, unabhängig davon, welcher Code-Pfad sie anlegt.

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/client.py backend/app/core/migrations.py backend/app/schemas/client.py backend/app/routers/clients.py backend/tests/test_clients_router.py
git commit -m "feat: add checkin_token, coach_private_note, email, checkin_reminder_days to Client"
```

---

### Task 2: `CheckinSubmission`-Modell + `Photo.checkin_submission_id`

**Files:**
- Create: `backend/app/models/checkin_submission.py`
- Modify: `backend/app/models/photo.py`
- Modify: `backend/app/models/client.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/core/migrations.py` (bereits in Task 1 erledigt - `photos.checkin_submission_id` steht schon in `_PENDING_COLUMNS`)

- [ ] **Step 1: `CheckinSubmission`-Modell anlegen**

```python
# backend/app/models/checkin_submission.py
"""
CheckinSubmission = eine vom Klienten über den Magic-Link (siehe
routers/public_checkin.py) eingereichte Check-in-Meldung. Schlanke
"Posteingang"-Schicht oberhalb von DayLog/Photo (siehe Design-Spec
Abschnitt "Architektur-Entscheidung") - schreibt zusätzlich ganz normal
in DayLog/Photo, ist selbst aber der Anker für Review-Status und
Coach-Feedback.
"""
import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CheckinStatus(str, enum.Enum):
    PENDING = "pending"
    REVIEWED = "reviewed"


class CheckinSubmission(Base):
    __tablename__ = "checkin_submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    client_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[CheckinStatus] = mapped_column(
        Enum(CheckinStatus), default=CheckinStatus.PENDING, nullable=False, index=True
    )
    coach_feedback_text: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    coach_feedback_video_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    photos: Mapped[list["Photo"]] = relationship(  # noqa: F821
        back_populates="checkin_submission"
    )

    def __repr__(self) -> str:
        return f"<CheckinSubmission id={self.id} client_id={self.client_id} status={self.status}>"
```

- [ ] **Step 2: `Photo` um `checkin_submission_id` erweitern**

In `backend/app/models/photo.py`, nach dem bestehenden `day_log`-Feld ergänzen:

```python
    checkin_submission_id: Mapped[int | None] = mapped_column(
        ForeignKey("checkin_submissions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    checkin_submission: Mapped["CheckinSubmission"] = relationship(  # noqa: F821
        back_populates="photos"
    )
```

- [ ] **Step 3: In `backend/app/models/__init__.py` registrieren**

Analog zu Pose/DayLog/Photo, damit `Base.metadata.create_all` die Tabelle bei einer frischen DB anlegt:

```python
from app.models.pose import Pose
from app.models.day_log import DayLog
from app.models.photo import Photo, ProcessingStatus
from app.models.checkin_submission import CheckinSubmission, CheckinStatus

__all__ = ["Pose", "DayLog", "Photo", "ProcessingStatus", "CheckinSubmission", "CheckinStatus"]
```

- [ ] **Step 4: Typprüfung / Import-Smoke-Test**

Run: `cd backend && .venv/Scripts/python -c "import app.main"`
Expected: kein Fehler (bestätigt, dass alle Relationship-String-Referenzen - `"CheckinSubmission"`, `"Photo"` - zur Laufzeit auflösbar sind).

- [ ] **Step 5: Backend-Suite laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: alle bisherigen Tests weiterhin grün (neue Tabelle bricht nichts Bestehendes).

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/checkin_submission.py backend/app/models/photo.py backend/app/models/__init__.py
git commit -m "feat: add CheckinSubmission model + Photo.checkin_submission_id"
```

---

### Task 3: Pydantic-Schemas für Check-ins

**Files:**
- Create: `backend/app/schemas/checkin.py`

- [ ] **Step 1: Schema-Datei anlegen**

```python
# backend/app/schemas/checkin.py
from datetime import datetime

from pydantic import BaseModel

from app.models.checkin_submission import CheckinStatus
from app.schemas.photo import PhotoOut


class CheckinSubmissionOut(BaseModel):
    id: int
    submitted_at: datetime
    weight_kg: float | None
    client_note: str | None
    status: CheckinStatus
    coach_feedback_text: str | None
    coach_feedback_video_url: str | None
    reviewed_at: datetime | None
    photos: list[PhotoOut]

    class Config:
        from_attributes = True


class CheckinFeedbackUpdate(BaseModel):
    """Payload für die Coach-Antwort auf einen Check-in. Alle Felder
    optional - der Coach kann z.B. nur "als geprüft markieren" klicken,
    ohne Text/Link zu setzen, oder umgekehrt nur Feedback speichern ohne
    schon final abzuschließen."""

    coach_feedback_text: str | None = None
    coach_feedback_video_url: str | None = None
    mark_reviewed: bool = False


class PublicCheckinSubmissionOut(BaseModel):
    """Wie CheckinSubmissionOut, aber für die öffentliche Klienten-Ansicht
    - bewusst dasselbe Shape (Klient soll sein eigenes Feedback sehen),
    eigener Typ nur zur klaren Trennung von der Coach-Route."""

    id: int
    submitted_at: datetime
    weight_kg: float | None
    client_note: str | None
    status: CheckinStatus
    coach_feedback_text: str | None
    coach_feedback_video_url: str | None
    photos: list[PhotoOut]

    class Config:
        from_attributes = True


class PublicCheckinPageOut(BaseModel):
    client_name: str
    submissions: list[PublicCheckinSubmissionOut]
```

- [ ] **Step 2: Import-Smoke-Test**

Run: `cd backend && .venv/Scripts/python -c "import app.schemas.checkin"`
Expected: kein Fehler.

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/checkin.py
git commit -m "feat: add CheckinSubmission Pydantic schemas"
```

---

## Part 2 — Backend: Öffentlicher Magic-Link-Endpunkt

### Task 4: Public Router - Check-in-Seite laden (`GET /api/public/checkin/{token}`)

**Files:**
- Create: `backend/app/routers/public_checkin.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_public_checkin_router.py`

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_public_checkin_router.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_public_checkin_router.py -v`
Expected: FAIL (`404 Not Found` für die Route selbst, da der Router noch nicht existiert/registriert ist).

- [ ] **Step 3: Router implementieren**

```python
# backend/app/routers/public_checkin.py
"""
Öffentlicher, passwortloser Zugang für Klienten: Check-in einreichen und
eigene Historie/Coach-Feedback einsehen - siehe Design-Spec Abschnitt
"Magic-Link-Mechanismus". Auth läuft NICHT über das Session-Cookie,
sondern über den opaken `Client.checkin_token` in der URL.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.client import Client
from app.models.checkin_submission import CheckinSubmission
from app.schemas.checkin import PublicCheckinPageOut

router = APIRouter(prefix="/api/public/checkin", tags=["public-checkin"])


def get_client_by_checkin_token(token: str, db: Session = Depends(get_db)) -> Client:
    """Analog zu `get_owned_client` in routers/clients.py, aber für den
    öffentlichen Zugang: lädt den Client NUR über den Magic-Link-Token,
    keine Session nötig. 404 bei unbekanntem/regeneriertem Token."""
    client_row = db.query(Client).filter(Client.checkin_token == token).first()
    if client_row is None:
        raise HTTPException(404, "Link ungültig")
    return client_row


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
    return PublicCheckinPageOut(client_name=client_row.name, submissions=submissions)
```

- [ ] **Step 4: Router in `main.py` registrieren**

In `backend/app/main.py`: Import und `include_router` ergänzen.

```python
from app.routers import auth, clients, comparisons, day_logs, photos, poses, public_checkin, settings as settings_router
```

```python
app.include_router(public_checkin.router)
```

- [ ] **Step 5: Tests laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_public_checkin_router.py -v`
Expected: alle PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/public_checkin.py backend/app/main.py backend/tests/test_public_checkin_router.py
git commit -m "feat: add public GET /api/public/checkin/{token} endpoint"
```

---

### Task 5: Public Router - Check-in einreichen (`POST /api/public/checkin/{token}/submit`)

**Files:**
- Modify: `backend/app/routers/public_checkin.py`
- Modify: `backend/app/services/email.py`
- Test: `backend/tests/test_public_checkin_router.py`

- [ ] **Step 1: Failing tests**

Append to `backend/tests/test_public_checkin_router.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_public_checkin_router.py -k submit -v`
Expected: FAIL (`405 Method Not Allowed` - POST-Route existiert noch nicht).

- [ ] **Step 3: E-Mail-Template für Coach-Benachrichtigung**

In `backend/app/services/email.py` ergänzen:

```python
def send_checkin_submitted_email(*, to: str, client_name: str, checkins_url: str) -> None:
    html = _base_email_html(
        "Neuer Check-in eingereicht",
        f"""
        <p><strong>{client_name}</strong> hat gerade einen neuen Check-in eingereicht.</p>
        <p><a href="{checkins_url}">Jetzt ansehen</a></p>
        """,
    )
    resend.Emails.send({
        "from": settings.email_from_address,
        "to": [to],
        "subject": f"Neuer Check-in von {client_name} - BodyComp Tracker",
        "html": html,
    })
```

- [ ] **Step 4: `POST /{token}/submit` implementieren**

In `backend/app/routers/public_checkin.py` ergänzen (Imports oben erweitern):

```python
import logging
import shutil
from datetime import date as date_
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import RateLimiter
from app.models.client import Client
from app.models.checkin_submission import CheckinSubmission
from app.models.day_log import DayLog
from app.schemas.checkin import CheckinSubmissionOut, PublicCheckinPageOut
from app.services.email import send_checkin_submitted_email
from app.services.folder_sync import sync_incoming_folder
from app.services.storage_paths import incoming_dir_for_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/public/checkin", tags=["public-checkin"])

# Großzügig genug für normale Nutzung (mehrmals täglich in Contest Prep
# denkbar, siehe Design-Spec), verhindert aber Missbrauch des
# unauthentifizierten Endpunkts.
checkin_submit_rate_limit = RateLimiter(max_requests=30, window_seconds=3600)


# ... get_client_by_checkin_token, get_checkin_page bleiben unverändert ...


@router.post("/{token}/submit", response_model=CheckinSubmissionOut, status_code=201)
def submit_checkin(
    weight_kg: float | None = Form(default=None),
    client_note: str | None = Form(default=None),
    files: list[UploadFile] = File(default=[]),
    client_row: Client = Depends(get_client_by_checkin_token),
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(checkin_submit_rate_limit),
):
    submission = CheckinSubmission(
        client_id=client_row.id, weight_kg=weight_kg, client_note=client_note
    )
    db.add(submission)
    db.flush()

    # Gewicht/Notiz landen im DayLog des HEUTIGEN Datums (der Klient
    # berichtet "heute geht es mir so", unabhängig vom EXIF-Datum
    # eventuell mitgeschickter Fotos - die werden unten separat und
    # unverändert nach ihrem eigenen Aufnahmedatum einsortiert).
    if weight_kg is not None or client_note:
        today = date_.today()
        day_log = (
            db.query(DayLog)
            .filter(DayLog.client_id == client_row.id, DayLog.date == today)
            .first()
        )
        if day_log is None:
            day_log = DayLog(client_id=client_row.id, date=today)
            db.add(day_log)
        if weight_kg is not None:
            day_log.weight_kg = weight_kg
        if client_note:
            day_log.notes = client_note

    db.commit()

    # Fotos wie beim normalen Upload (routers/photos.py upload_photos)
    # nach photos_incoming/<client_id>/ kopieren und dieselbe
    # Sync-Pipeline nutzen (EXIF/HEIC/Thumbnail-Handling) - dann die neu
    # entstandenen Photo-Rows dieser Einreichung zuordnen. Pose-Zuordnung
    # bleibt bewusst Coach-Aufgabe im bestehenden Import-Screen.
    if files:
        incoming_dir = incoming_dir_for_client(client_row.id)
        incoming_dir.mkdir(parents=True, exist_ok=True)
        for upload in files:
            if not upload.filename:
                continue
            suffix = Path(upload.filename).suffix.lower()
            if suffix not in settings.allowed_extensions:
                continue
            dest = incoming_dir / upload.filename
            counter = 1
            while dest.exists():
                dest = incoming_dir / f"{Path(upload.filename).stem}_{counter}{suffix}"
                counter += 1
            with dest.open("wb") as f:
                shutil.copyfileobj(upload.file, f)

        new_photos = sync_incoming_folder(db, client_row.id)
        for photo in new_photos:
            photo.checkin_submission_id = submission.id
        db.commit()

    db.refresh(submission)

    # Coach-Benachrichtigung - best effort, ein Mail-Fehler soll die
    # erfolgreich gespeicherte Einreichung nicht rückgängig machen.
    try:
        checkins_url = f"{settings.frontend_base_url}/clients/{client_row.id}/checkins"
        send_checkin_submitted_email(
            to=client_row.owner.email, client_name=client_row.name, checkins_url=checkins_url
        )
    except Exception:
        logger.warning("Konnte Check-in-Benachrichtigung nicht senden", exc_info=True)

    return submission
```

- [ ] **Step 5: Tests laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_public_checkin_router.py -v`
Expected: alle PASS.

- [ ] **Step 6: `_reset_rate_limits`-Fixture erweitern**

In `backend/tests/conftest.py`, damit der neue Rate-Limiter zwischen Tests zurückgesetzt wird:

```python
@pytest.fixture(autouse=True)
def _reset_rate_limits():
    auth_router.signup_rate_limit._hits.clear()
    auth_router.login_rate_limit._hits.clear()
    auth_router.resend_verification_rate_limit._hits.clear()
    from app.routers import public_checkin as public_checkin_router
    public_checkin_router.checkin_submit_rate_limit._hits.clear()
    yield
```

- [ ] **Step 7: Volle Suite laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: alle grün.

- [ ] **Step 8: Commit**

```bash
git add backend/app/routers/public_checkin.py backend/app/services/email.py backend/tests/test_public_checkin_router.py backend/tests/conftest.py
git commit -m "feat: add public checkin submission endpoint + coach notification email"
```

---

## Part 3 — Backend: Coach-seitige Endpunkte

### Task 6: Checkins-Router (Coach-Review: Liste + Feedback)

**Files:**
- Create: `backend/app/routers/checkins.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_checkins_router.py`

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_checkins_router.py
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


def test_list_checkins_returns_pending_first(client, db_session):
    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()

    db_session.add(CheckinSubmission(client_id=created["id"], status=CheckinStatus.REVIEWED))
    db_session.add(CheckinSubmission(client_id=created["id"], status=CheckinStatus.PENDING))
    db_session.commit()

    response = client.get(f"/api/clients/{created['id']}/checkins")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["status"] == "pending"


def test_list_checkins_for_foreign_client_returns_404(client, db_session):
    _login(client, db_session, email="a@b.com")
    created = client.post("/api/clients", json={"name": "Max"}).json()
    client.post("/api/auth/logout")

    _login(client, db_session, email="c@d.com")
    response = client.get(f"/api/clients/{created['id']}/checkins")
    assert response.status_code == 404


def test_update_checkin_sets_feedback_and_marks_reviewed(client, db_session):
    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()

    submission = CheckinSubmission(client_id=created["id"])
    db_session.add(submission)
    db_session.commit()
    db_session.refresh(submission)

    response = client.patch(
        f"/api/clients/{created['id']}/checkins/{submission.id}",
        json={
            "coach_feedback_text": "Sieht gut aus!",
            "coach_feedback_video_url": "https://loom.com/share/xyz",
            "mark_reviewed": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "reviewed"
    assert body["coach_feedback_text"] == "Sieht gut aus!"
    assert body["reviewed_at"] is not None


def test_update_checkin_not_found_returns_404(client, db_session):
    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()

    response = client.patch(
        f"/api/clients/{created['id']}/checkins/9999", json={"mark_reviewed": True}
    )
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_checkins_router.py -v`
Expected: FAIL (404 für Route, da Router noch nicht existiert - `test_list_checkins_for_foreign_client_returns_404` liefert zwar zufällig auch 404, aber aus dem falschen Grund; nach Implementierung muss der Rest ebenfalls grün werden).

- [ ] **Step 3: Router implementieren**

```python
# backend/app/routers/checkins.py
"""
Coach-seitige Review-Ansicht der Check-in-Einreichungen eines Klienten -
siehe Design-Spec Abschnitt "Coach-Ansicht". Nutzt dieselbe
`get_owned_client`-Dependency wie alle anderen client-gescopten Router,
damit ein Coach nie auf fremde Klienten zugreifen kann.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.checkin_submission import CheckinStatus, CheckinSubmission
from app.models.client import Client
from app.routers.clients import get_owned_client
from app.schemas.checkin import CheckinFeedbackUpdate, CheckinSubmissionOut

router = APIRouter(prefix="/api/clients/{client_id}/checkins", tags=["checkins"])


@router.get("", response_model=list[CheckinSubmissionOut])
def list_checkins(client_row: Client = Depends(get_owned_client), db: Session = Depends(get_db)):
    submissions = (
        db.query(CheckinSubmission).filter(CheckinSubmission.client_id == client_row.id).all()
    )
    # Offene zuerst (neueste zuerst innerhalb der jeweiligen Gruppe) -
    # Python-seitig sortiert, da eine SQL-ORDER-BY-Klausel über einen
    # String-Enum-Vergleich fragil gegenüber künftigen Statuswerten wäre.
    submissions.sort(
        key=lambda s: (s.status != CheckinStatus.PENDING, -(s.submitted_at.timestamp()))
    )
    return submissions


@router.patch("/{checkin_id}", response_model=CheckinSubmissionOut)
def update_checkin(
    checkin_id: int,
    payload: CheckinFeedbackUpdate,
    client_row: Client = Depends(get_owned_client),
    db: Session = Depends(get_db),
):
    submission = (
        db.query(CheckinSubmission)
        .filter(CheckinSubmission.id == checkin_id, CheckinSubmission.client_id == client_row.id)
        .first()
    )
    if submission is None:
        raise HTTPException(404, "Check-in nicht gefunden")

    if payload.coach_feedback_text is not None:
        submission.coach_feedback_text = payload.coach_feedback_text
    if payload.coach_feedback_video_url is not None:
        submission.coach_feedback_video_url = payload.coach_feedback_video_url
    if payload.mark_reviewed:
        submission.status = CheckinStatus.REVIEWED
        submission.reviewed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(submission)
    return submission
```

- [ ] **Step 4: Router registrieren**

In `backend/app/main.py`:

```python
from app.routers import auth, checkins, clients, comparisons, day_logs, photos, poses, public_checkin, settings as settings_router
```

```python
app.include_router(checkins.router)
```

- [ ] **Step 5: Tests laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_checkins_router.py -v`
Expected: alle PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/checkins.py backend/app/main.py backend/tests/test_checkins_router.py
git commit -m "feat: add coach-facing checkins list/feedback endpoints"
```

---

### Task 7: Magic-Link neu generieren

**Files:**
- Modify: `backend/app/routers/clients.py`
- Test: `backend/tests/test_clients_router.py`

- [ ] **Step 1: Failing test**

Append to `backend/tests/test_clients_router.py`:

```python
def test_regenerate_checkin_token_changes_token(client, db_session):
    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()
    old_token = created["checkin_token"]

    response = client.post(f"/api/clients/{created['id']}/checkin-token/regenerate")
    assert response.status_code == 200
    new_token = response.json()["checkin_token"]
    assert new_token != old_token

    # Alter Link ist danach ungültig.
    old_link_check = client.get(f"/api/public/checkin/{old_token}")
    assert old_link_check.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_clients_router.py -k regenerate -v`
Expected: FAIL (404, Route existiert noch nicht).

- [ ] **Step 3: Endpunkt ergänzen**

In `backend/app/routers/clients.py`, `import secrets` oben ergänzen und Endpoint hinzufügen (nach `update_client`):

```python
@router.post("/{client_id}/checkin-token/regenerate", response_model=ClientOut)
def regenerate_checkin_token(
    client_row: Client = Depends(get_owned_client), db: Session = Depends(get_db)
):
    """Invalidiert den alten Magic-Link sofort (z.B. falls versehentlich
    geteilt) - siehe Design-Spec Abschnitt "Magic-Link-Mechanismus"."""
    client_row.checkin_token = secrets.token_urlsafe(24)
    db.commit()
    db.refresh(client_row)
    return _to_client_out(client_row, db)
```

- [ ] **Step 4: Test laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_clients_router.py -v`
Expected: alle PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/clients.py backend/tests/test_clients_router.py
git commit -m "feat: add checkin-token regeneration endpoint"
```

---

### Task 8: Dashboard-Aggregation - `pending_checkins_count` in `list_clients`

**Files:**
- Modify: `backend/app/routers/clients.py`
- Test: `backend/tests/test_clients_router.py`

- [ ] **Step 1: Failing test**

Append to `backend/tests/test_clients_router.py`:

```python
def test_list_clients_includes_pending_checkins_count(client, db_session):
    from app.models.checkin_submission import CheckinStatus, CheckinSubmission

    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()

    db_session.add(CheckinSubmission(client_id=created["id"], status=CheckinStatus.PENDING))
    db_session.add(CheckinSubmission(client_id=created["id"], status=CheckinStatus.PENDING))
    db_session.add(CheckinSubmission(client_id=created["id"], status=CheckinStatus.REVIEWED))
    db_session.commit()

    response = client.get("/api/clients")
    body = response.json()
    match = next(c for c in body if c["id"] == created["id"])
    assert match["pending_checkins_count"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_clients_router.py -k pending_checkins_count -v`
Expected: FAIL (`assert 0 == 2`, da `list_clients` den Default `0` nutzt).

- [ ] **Step 3: `_to_client_out` um echte `pending_checkins_count`-Berechnung erweitern**

Damit `POST/GET/PATCH /api/clients/{id}` (einzelner Client) nicht dauerhaft
den Platzhalter-Default `0` aus Task 1 zurückgeben, sondern denselben
echten Wert wie `list_clients` - `_to_client_out` berechnet `photo_count`/
`last_activity_dt` bereits eigenständig per Einzel-Query, das wird hier
um dieselbe Berechnung für `pending_checkins_count` ergänzt:

```python
def _to_client_out(client_row: Client, db: Session) -> ClientOut:
    from sqlalchemy import func

    from app.models.checkin_submission import CheckinStatus, CheckinSubmission
    from app.models.photo import Photo

    photo_count = (
        db.query(func.count(Photo.id)).filter(Photo.client_id == client_row.id).scalar() or 0
    )
    last_activity_dt = (
        db.query(func.max(Photo.taken_at)).filter(Photo.client_id == client_row.id).scalar()
    )
    pending_checkins_count = (
        db.query(func.count(CheckinSubmission.id))
        .filter(
            CheckinSubmission.client_id == client_row.id,
            CheckinSubmission.status == CheckinStatus.PENDING,
        )
        .scalar()
        or 0
    )
    return _client_row_to_out(client_row, photo_count, last_activity_dt, pending_checkins_count)
```

- [ ] **Step 4: `list_clients` um gebatchte Aggregation erweitern**

In `backend/app/routers/clients.py`, `list_clients` anpassen:

```python
@router.get("", response_model=list[ClientOut])
def list_clients(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    from sqlalchemy import func

    from app.models.checkin_submission import CheckinStatus, CheckinSubmission
    from app.models.photo import Photo

    clients = (
        db.query(Client)
        .filter(Client.owner_id == current_user.id)
        .order_by(Client.created_at)
        .all()
    )

    client_ids = [c.id for c in clients]
    stats = dict(
        db.query(Photo.client_id, func.count(Photo.id))
        .filter(Photo.client_id.in_(client_ids))
        .group_by(Photo.client_id)
        .all()
    )
    last_activity = dict(
        db.query(Photo.client_id, func.max(Photo.taken_at))
        .filter(Photo.client_id.in_(client_ids))
        .group_by(Photo.client_id)
        .all()
    )
    pending_checkins = dict(
        db.query(CheckinSubmission.client_id, func.count(CheckinSubmission.id))
        .filter(
            CheckinSubmission.client_id.in_(client_ids),
            CheckinSubmission.status == CheckinStatus.PENDING,
        )
        .group_by(CheckinSubmission.client_id)
        .all()
    )

    return [
        _client_row_to_out(
            c, stats.get(c.id, 0), last_activity.get(c.id), pending_checkins.get(c.id, 0)
        )
        for c in clients
    ]
```

- [ ] **Step 5: Test laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_clients_router.py -v`
Expected: alle PASS.

- [ ] **Step 6: Volle Backend-Suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: alle grün.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/clients.py backend/tests/test_clients_router.py
git commit -m "feat: include pending_checkins_count in list_clients and _to_client_out"
```

---

## Part 4 — Backend: Erinnerungsmails

### Task 9: Erinnerungs-E-Mail-Template + Reminder-Service

**Files:**
- Modify: `backend/app/services/email.py`
- Create: `backend/app/services/checkin_reminders.py`
- Test: `backend/tests/test_checkin_reminders.py`

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_checkin_reminders.py
from datetime import datetime, timedelta, timezone

from app.models.checkin_submission import CheckinSubmission
from app.models.client import Client
from app.models.user import User
from app.services.auth import hash_password
from app.services.checkin_reminders import run_checkin_reminders


def _make_user_and_client(db_session, **client_kwargs):
    user = User(
        email="coach@example.com",
        password_hash=hash_password("pw12345"),
        display_name="Coach",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.flush()
    client_row = Client(owner_id=user.id, name="Max", **client_kwargs)
    db_session.add(client_row)
    db_session.commit()
    db_session.refresh(client_row)
    return user, client_row


def test_sends_reminder_when_no_submission_ever_and_threshold_passed(db_session, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.checkin_reminders.send_checkin_reminder_email",
        lambda **kwargs: sent.append(kwargs),
    )

    _, client_row = _make_user_and_client(
        db_session, email="max@example.com", checkin_reminder_days=7
    )
    client_row.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    db_session.commit()

    count = run_checkin_reminders(db_session)

    assert count == 1
    assert sent[0]["to"] == "max@example.com"


def test_no_reminder_when_checkin_reminder_days_not_set(db_session, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.checkin_reminders.send_checkin_reminder_email",
        lambda **kwargs: sent.append(kwargs),
    )
    _, client_row = _make_user_and_client(db_session, email="max@example.com")
    client_row.created_at = datetime.now(timezone.utc) - timedelta(days=30)
    db_session.commit()

    assert run_checkin_reminders(db_session) == 0
    assert sent == []


def test_no_reminder_when_no_email_on_file(db_session, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.checkin_reminders.send_checkin_reminder_email",
        lambda **kwargs: sent.append(kwargs),
    )
    _, client_row = _make_user_and_client(db_session, checkin_reminder_days=7)
    client_row.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    db_session.commit()

    assert run_checkin_reminders(db_session) == 0
    assert sent == []


def test_no_reminder_when_recent_submission_exists(db_session, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.checkin_reminders.send_checkin_reminder_email",
        lambda **kwargs: sent.append(kwargs),
    )
    _, client_row = _make_user_and_client(
        db_session, email="max@example.com", checkin_reminder_days=7
    )
    db_session.add(CheckinSubmission(
        client_id=client_row.id,
        submitted_at=datetime.now(timezone.utc) - timedelta(days=1),
    ))
    db_session.commit()

    assert run_checkin_reminders(db_session) == 0
    assert sent == []


def test_no_duplicate_reminder_within_the_same_window(db_session, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.checkin_reminders.send_checkin_reminder_email",
        lambda **kwargs: sent.append(kwargs),
    )
    _, client_row = _make_user_and_client(
        db_session, email="max@example.com", checkin_reminder_days=7
    )
    client_row.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    client_row.last_reminder_sent_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()

    assert run_checkin_reminders(db_session) == 0
    assert sent == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_checkin_reminders.py -v`
Expected: FAIL (`ModuleNotFoundError: app.services.checkin_reminders`).

- [ ] **Step 3: E-Mail-Template ergänzen**

In `backend/app/services/email.py`:

```python
def send_checkin_reminder_email(*, to: str, checkin_url: str) -> None:
    html = _base_email_html(
        "Zeit für deinen nächsten Check-in",
        f"""
        <p>Dein Coach wartet auf deinen nächsten Check-in - reich ihn hier ein:</p>
        <p><a href="{checkin_url}">{checkin_url}</a></p>
        """,
    )
    resend.Emails.send({
        "from": settings.email_from_address,
        "to": [to],
        "subject": "Zeit für deinen Check-in - BodyComp Tracker",
        "html": html,
    })
```

- [ ] **Step 4: Reminder-Service implementieren**

```python
# backend/app/services/checkin_reminders.py
"""
Erinnerungsmails an Klienten ohne aktuellen Check-in - siehe Design-Spec
Abschnitt "Benachrichtigungen". Reine, testbare Funktion (kein Scheduler-
Code hier) - siehe core/scheduler.py für die tägliche Cron-Anbindung.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.checkin_submission import CheckinSubmission
from app.models.client import Client
from app.services.email import send_checkin_reminder_email


def run_checkin_reminders(db: Session) -> int:
    """Prüft jeden Client mit gesetzter `email` UND `checkin_reminder_days`:
    wurde seit der letzten Einreichung (oder seit Account-Erstellung, falls
    noch nie eingereicht) länger als die konfigurierte Schwelle nichts
    mehr eingereicht, UND liegt die letzte Erinnerung selbst mindestens
    genauso lange zurück (verhindert tägliches Spamming, sobald die
    Schwelle einmal überschritten ist), wird eine Erinnerungsmail
    verschickt. Gibt die Anzahl verschickter Mails zurück."""
    now = datetime.now(timezone.utc)
    candidates = (
        db.query(Client)
        .filter(Client.email.isnot(None), Client.checkin_reminder_days.isnot(None))
        .all()
    )

    sent_count = 0
    for client_row in candidates:
        last_submission = (
            db.query(CheckinSubmission)
            .filter(CheckinSubmission.client_id == client_row.id)
            .order_by(CheckinSubmission.submitted_at.desc())
            .first()
        )
        reference_point = last_submission.submitted_at if last_submission else client_row.created_at
        if reference_point.tzinfo is None:
            reference_point = reference_point.replace(tzinfo=timezone.utc)

        days_since_reference = (now - reference_point).days
        if days_since_reference < client_row.checkin_reminder_days:
            continue

        if client_row.last_reminder_sent_at is not None:
            last_reminder = client_row.last_reminder_sent_at
            if last_reminder.tzinfo is None:
                last_reminder = last_reminder.replace(tzinfo=timezone.utc)
            days_since_last_reminder = (now - last_reminder).days
            if days_since_last_reminder < client_row.checkin_reminder_days:
                continue

        checkin_url = f"{settings.frontend_base_url}/checkin/{client_row.checkin_token}"
        send_checkin_reminder_email(to=client_row.email, checkin_url=checkin_url)
        client_row.last_reminder_sent_at = now
        sent_count += 1

    db.commit()
    return sent_count
```

- [ ] **Step 5: Tests laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_checkin_reminders.py -v`
Expected: alle PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/email.py backend/app/services/checkin_reminders.py backend/tests/test_checkin_reminders.py
git commit -m "feat: add checkin reminder service + email template"
```

---

### Task 10: Täglicher Scheduler-Job (APScheduler)

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/app/core/scheduler.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Dependency ergänzen**

In `backend/requirements.txt`, nach `resend>=2.5.1` ergänzen:

```
apscheduler>=3.10.4
```

Run: `cd backend && .venv/Scripts/pip install apscheduler>=3.10.4`

- [ ] **Step 2: Scheduler-Setup**

```python
# backend/app/core/scheduler.py
"""
Täglicher Hintergrund-Job für Check-in-Erinnerungen - siehe Design-Spec
Abschnitt "Benachrichtigungen". In-Process (APScheduler BackgroundScheduler,
läuft in einem eigenen Thread) statt externem Cron, weil die App aktuell
als Single-Process-Deployment läuft (siehe core/rate_limit.py für dieselbe
Design-Entscheidung an anderer Stelle) - für Stufe 3 (Mehrserver-Hosting)
müsste das auf einen verteilten Scheduler wechseln.
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)


def _run_reminders_job() -> None:
    # Lazy-Import von main, damit zur Laufzeit (nicht beim Modul-Import)
    # aufgelöst wird, welche SessionLocal aktuell gilt - wichtig, weil
    # tests/conftest.py `app.main.SessionLocal` pro Test durch eine
    # frische Test-DB-Session-Factory ersetzt (siehe dortige Doku).
    import app.main as main_module
    from app.services.checkin_reminders import run_checkin_reminders

    db = main_module.SessionLocal()
    try:
        sent = run_checkin_reminders(db)
        if sent:
            logger.info("Check-in-Erinnerungen verschickt: %d", sent)
    except Exception:
        logger.exception("Check-in-Erinnerungs-Job fehlgeschlagen")
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(_run_reminders_job, "cron", hour=9, minute=0, id="checkin_reminders")
    scheduler.start()
    return scheduler
```

- [ ] **Step 3: In `main.py` lifespan einhängen**

```python
from app.core.scheduler import start_scheduler
```

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    run_lightweight_migrations(engine)
    fix_users_password_hash_nullable(engine)
    scheduler = start_scheduler()
    yield
    scheduler.shutdown()
```

- [ ] **Step 4: Smoke-Test - App startet weiterhin sauber**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: alle Tests weiterhin grün (jeder Test öffnet/schließt die App via `TestClient`-Context-Manager, was den Scheduler pro Test kurz startet/stoppt - das darf nichts kaputt machen, da der Cron-Trigger erst um 9 Uhr feuert und `scheduler.shutdown()` sauber beendet, ohne auf laufende Jobs zu warten, da keiner läuft).

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt backend/app/core/scheduler.py backend/app/main.py
git commit -m "feat: wire daily checkin reminder job via APScheduler"
```

---

## Part 5 — Frontend: Typen & API-Client

### Task 11: Types + `api`-Client-Erweiterungen

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: `Client`-Interface erweitern + `CheckinSubmission`-Typ ergänzen**

In `frontend/src/types/index.ts`:

```typescript
export interface Client {
  id: number;
  name: string;
  height_cm: number | null;
  birth_date: string | null; // ISO YYYY-MM-DD
  gender: string | null;
  start_date: string | null;
  created_at: string;
  photo_count: number;
  last_activity: string | null; // ISO YYYY-MM-DD
  pending_checkins_count: number;
  checkin_token: string;
  coach_private_note: string | null;
  email: string | null;
  checkin_reminder_days: number | null;
}
```

Am Ende der Datei (nach `UnprocessedPhoto`) ergänzen:

```typescript
export type CheckinStatus = "pending" | "reviewed";

export interface CheckinSubmission {
  id: number;
  submitted_at: string; // ISO datetime
  weight_kg: number | null;
  client_note: string | null;
  status: CheckinStatus;
  coach_feedback_text: string | null;
  coach_feedback_video_url: string | null;
  reviewed_at: string | null;
  photos: Photo[];
}

export interface PublicCheckinPage {
  client_name: string;
  submissions: Omit<CheckinSubmission, "reviewed_at">[];
}
```

- [ ] **Step 2: `api`-Client erweitern**

In `frontend/src/api/client.ts`: Import erweitern und neue Bereiche ergänzen.

```typescript
import type { CheckinSubmission, Client, DayLog, Photo, Pose, PublicCheckinPage, UnprocessedPhoto } from "../types";
```

`clients.create`/`clients.update` bekommen die neuen optionalen Felder in der Payload-Signatur:

```typescript
  clients: {
    list: () => client.get<Client[]>("/clients").then((r) => r.data),
    get: (clientId: number) => client.get<Client>(`/clients/${clientId}`).then((r) => r.data),
    create: (payload: {
      name: string;
      height_cm?: number | null;
      birth_date?: string | null;
      gender?: string | null;
      start_date?: string | null;
    }) => client.post<Client>("/clients", payload).then((r) => r.data),
    update: (
      clientId: number,
      payload: Partial<Omit<Client, "id" | "created_at" | "checkin_token" | "photo_count" | "last_activity" | "pending_checkins_count">>
    ) => client.patch<Client>(`/clients/${clientId}`, payload).then((r) => r.data),
    regenerateCheckinToken: (clientId: number) =>
      client.post<Client>(`/clients/${clientId}/checkin-token/regenerate`).then((r) => r.data),
  },
```

Neuer Top-Level-Bereich `checkins` und `publicCheckin` (am Ende des `api`-Objekts, vor der schließenden Klammer):

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
  },
  publicCheckin: {
    get: (token: string) =>
      client.get<PublicCheckinPage>(`/public/checkin/${token}`).then((r) => r.data),
    submit: (token: string, payload: { weight_kg?: number | null; client_note?: string; files: File[] }) => {
      const form = new FormData();
      if (payload.weight_kg != null) form.append("weight_kg", String(payload.weight_kg));
      if (payload.client_note) form.append("client_note", payload.client_note);
      for (const file of payload.files) form.append("files", file);
      return client
        .post<CheckinSubmission>(`/public/checkin/${token}/submit`, form, {
          headers: { "Content-Type": "multipart/form-data" },
        })
        .then((r) => r.data);
    },
  },
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/client.ts
git commit -m "feat: add CheckinSubmission types + api client methods"
```

---

## Part 6 — Frontend: Klienten-Ansicht (öffentliche Seite)

### Task 12: `CheckinSubmit.tsx` (öffentliche Einreichungsseite) + Route

**Files:**
- Create: `frontend/src/pages/CheckinSubmit.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Seite implementieren**

```tsx
// frontend/src/pages/CheckinSubmit.tsx
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { api, mediaUrl } from "../api/client";

/**
 * Öffentliche, passwortlose Seite für Klienten - siehe Design-Spec
 * Abschnitt "Klienten-Ansicht". Bewusst KEIN AppShell/ClientShell: diese
 * Seite ist eigenständig, handy-tauglich und für jeden mit dem Link
 * erreichbar, unabhängig vom eingeloggten Coach-Zustand im selben Browser.
 */
export default function CheckinSubmit() {
  const { token } = useParams<{ token: string }>();
  const queryClient = useQueryClient();
  const [weightKg, setWeightKg] = useState("");
  const [note, setNote] = useState("");
  const [files, setFiles] = useState<File[]>([]);

  const pageQuery = useQuery({
    queryKey: ["public-checkin", token],
    queryFn: () => api.publicCheckin.get(token!),
    enabled: !!token,
  });

  const submitMutation = useMutation({
    mutationFn: () =>
      api.publicCheckin.submit(token!, {
        weight_kg: weightKg.trim() === "" ? null : Number(weightKg),
        client_note: note.trim() === "" ? undefined : note.trim(),
        files,
      }),
    onSuccess: () => {
      setWeightKg("");
      setNote("");
      setFiles([]);
      queryClient.invalidateQueries({ queryKey: ["public-checkin", token] });
    },
  });

  if (pageQuery.isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4 text-slate-400">
        Lade…
      </div>
    );
  }

  if (pageQuery.isError || !pageQuery.data) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4">
        <p className="text-slate-400">Dieser Link ist ungültig oder abgelaufen.</p>
      </div>
    );
  }

  const page = pageQuery.data;

  return (
    <div className="min-h-screen bg-background px-4 py-8 text-slate-100">
      <div className="mx-auto max-w-md space-y-6">
        <div>
          <p className="text-xs text-slate-500">Check-in für</p>
          <h1 className="text-xl font-semibold text-white">{page.client_name}</h1>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            submitMutation.mutate();
          }}
          className="space-y-4 rounded-xl border border-white/5 bg-surface p-4"
        >
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Gewicht (kg)
            <input
              type="number"
              step="0.1"
              value={weightKg}
              onChange={(e) => setWeightKg(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Notiz (optional)
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={3}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Fotos (optional)
            <input
              type="file"
              multiple
              accept="image/jpeg,image/png,image/heic,.heic"
              onChange={(e) => setFiles(e.target.files ? Array.from(e.target.files) : [])}
              className="text-sm text-slate-400"
            />
          </label>
          {submitMutation.isError && (
            <p className="text-sm text-red-400">Einreichen fehlgeschlagen - bitte erneut versuchen.</p>
          )}
          <button
            type="submit"
            disabled={submitMutation.isPending}
            className="w-full rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-50"
          >
            {submitMutation.isPending ? "Sende…" : "Check-in einreichen"}
          </button>
        </form>

        <div className="space-y-3">
          <h2 className="text-sm font-medium text-slate-400">Meine bisherigen Check-ins</h2>
          {page.submissions.length === 0 && (
            <p className="text-sm text-slate-600">Noch keine Check-ins eingereicht.</p>
          )}
          {page.submissions.map((s) => (
            <div key={s.id} className="rounded-xl border border-white/5 bg-surface p-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-white">
                  {new Date(s.submitted_at).toLocaleDateString("de-DE")}
                </span>
                <span
                  className={`text-xs ${s.status === "reviewed" ? "text-accent" : "text-slate-500"}`}
                >
                  {s.status === "reviewed" ? "✅ Geprüft" : "⏳ Ausstehend"}
                </span>
              </div>
              {s.weight_kg != null && (
                <p className="mt-1 text-xs text-slate-500">{s.weight_kg} kg</p>
              )}
              {s.photos.length > 0 && (
                <div className="mt-2 flex gap-2 overflow-x-auto">
                  {s.photos.map((p) => (
                    <img
                      key={p.id}
                      src={mediaUrl(p.thumb_path)}
                      alt=""
                      className="h-16 w-16 shrink-0 rounded-lg object-cover"
                    />
                  ))}
                </div>
              )}
              {s.coach_feedback_text && (
                <p className="mt-2 text-sm text-slate-300">{s.coach_feedback_text}</p>
              )}
              {s.coach_feedback_video_url && (
                <a
                  href={s.coach_feedback_video_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1 inline-block text-sm text-accent hover:underline"
                >
                  Video-Feedback ansehen
                </a>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Route in `App.tsx` ergänzen**

Als öffentliche Route (außerhalb von `RequireAuth`), z.B. direkt nach `/reset-password`:

```tsx
import CheckinSubmit from "./pages/CheckinSubmit";
```

```tsx
<Route path="/checkin/:token" element={<CheckinSubmit />} />
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/CheckinSubmit.tsx frontend/src/App.tsx
git commit -m "feat: add public CheckinSubmit page + /checkin/:token route"
```

---

## Part 7 — Frontend: Coach-Ansicht

### Task 13: `ClientCheckins.tsx` (Check-ins-Tab) + Nav-Eintrag + Route

**Files:**
- Create: `frontend/src/pages/ClientCheckins.tsx`
- Modify: `frontend/src/components/ClientShell.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Seite implementieren**

```tsx
// frontend/src/pages/ClientCheckins.tsx
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { api, mediaUrl } from "../api/client";
import PageHeader from "../components/PageHeader";
import type { CheckinSubmission } from "../types";

function complianceRate(submissions: CheckinSubmission[]): string {
  const fourWeeksAgo = Date.now() - 28 * 24 * 60 * 60 * 1000;
  const recent = submissions.filter((s) => new Date(s.submitted_at).getTime() >= fourWeeksAgo);
  return `${recent.length} Check-ins in den letzten 4 Wochen`;
}

export default function ClientCheckins() {
  const { clientId } = useParams<{ clientId: string }>();
  const clientIdNum = Number(clientId);
  const queryClient = useQueryClient();
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [feedbackDrafts, setFeedbackDrafts] = useState<Record<number, { text: string; videoUrl: string }>>({});

  const checkinsQuery = useQuery({
    queryKey: ["checkins", clientIdNum],
    queryFn: () => api.checkins.list(clientIdNum),
  });

  const updateMutation = useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: number;
      payload: { coach_feedback_text?: string; coach_feedback_video_url?: string; mark_reviewed?: boolean };
    }) => api.checkins.update(clientIdNum, id, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["checkins", clientIdNum] }),
  });

  const checkins = checkinsQuery.data ?? [];
  const draftFor = (id: number, checkin: CheckinSubmission) =>
    feedbackDrafts[id] ?? {
      text: checkin.coach_feedback_text ?? "",
      videoUrl: checkin.coach_feedback_video_url ?? "",
    };

  return (
    <div className="space-y-6">
      <PageHeader title="Check-ins" />

      {checkins.length > 0 && (
        <p className="text-sm text-slate-500">{complianceRate(checkins)}</p>
      )}

      {checkinsQuery.isLoading && <p className="text-slate-500">Lade…</p>}

      {!checkinsQuery.isLoading && checkins.length === 0 && (
        <div className="rounded-xl border border-dashed border-white/10 p-8 text-center text-slate-500">
          Noch keine Check-ins eingereicht.
        </div>
      )}

      <div className="space-y-3">
        {checkins.map((checkin) => {
          const isOpen = expandedId === checkin.id;
          const draft = draftFor(checkin.id, checkin);
          return (
            <div key={checkin.id} className="rounded-xl border border-white/5 bg-surface p-4">
              <button
                onClick={() => setExpandedId(isOpen ? null : checkin.id)}
                className="flex w-full items-center justify-between text-left"
              >
                <span className="text-sm text-white">
                  {new Date(checkin.submitted_at).toLocaleString("de-DE")}
                  {checkin.weight_kg != null && (
                    <span className="ml-2 text-slate-500">{checkin.weight_kg} kg</span>
                  )}
                </span>
                <span
                  className={`text-xs font-medium ${
                    checkin.status === "pending" ? "text-amber-400" : "text-accent"
                  }`}
                >
                  {checkin.status === "pending" ? "⏳ Offen" : "✅ Geprüft"}
                </span>
              </button>

              {isOpen && (
                <div className="mt-4 space-y-3 border-t border-white/5 pt-4">
                  {checkin.client_note && (
                    <p className="text-sm text-slate-300">„{checkin.client_note}“</p>
                  )}
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
                  <label className="flex flex-col gap-1 text-sm text-slate-400">
                    Feedback
                    <textarea
                      value={draft.text}
                      onChange={(e) =>
                        setFeedbackDrafts((d) => ({
                          ...d,
                          [checkin.id]: { ...draft, text: e.target.value },
                        }))
                      }
                      rows={2}
                      className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-sm text-slate-400">
                    Video-Link (Loom o.ä.)
                    <input
                      value={draft.videoUrl}
                      onChange={(e) =>
                        setFeedbackDrafts((d) => ({
                          ...d,
                          [checkin.id]: { ...draft, videoUrl: e.target.value },
                        }))
                      }
                      placeholder="https://loom.com/share/…"
                      className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
                    />
                  </label>
                  <div className="flex gap-2">
                    <button
                      onClick={() =>
                        updateMutation.mutate({
                          id: checkin.id,
                          payload: {
                            coach_feedback_text: draft.text,
                            coach_feedback_video_url: draft.videoUrl,
                          },
                        })
                      }
                      disabled={updateMutation.isPending}
                      className="rounded-lg border border-white/10 px-3 py-1.5 text-xs font-medium text-white hover:bg-white/5 disabled:opacity-50"
                    >
                      Feedback speichern
                    </button>
                    {checkin.status === "pending" && (
                      <button
                        onClick={() =>
                          updateMutation.mutate({
                            id: checkin.id,
                            payload: {
                              coach_feedback_text: draft.text,
                              coach_feedback_video_url: draft.videoUrl,
                              mark_reviewed: true,
                            },
                          })
                        }
                        disabled={updateMutation.isPending}
                        className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-slate-900 hover:opacity-90 disabled:opacity-50"
                      >
                        Als geprüft markieren
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Nav-Eintrag in `ClientShell.tsx`**

In `frontend/src/components/ClientShell.tsx`, `NAV_ITEMS` erweitern:

```typescript
const NAV_ITEMS = [
  { to: "timeline", label: "Timeline", icon: "📅" },
  { to: "checkins", label: "Check-ins", icon: "✅" },
  { to: "unprocessed", label: "Import", icon: "📥" },
  { to: "compare", label: "Compare", icon: "🔍" },
  { to: "statistics", label: "Statistik", icon: "📊" },
  { to: "settings", label: "Settings", icon: "⚙️" },
];
```

Keine weiteren Änderungen nötig - `activeNavTo` und die Render-Logik iterieren bereits generisch über `NAV_ITEMS`.

- [ ] **Step 3: Route in `App.tsx` ergänzen**

```tsx
import ClientCheckins from "./pages/ClientCheckins";
```

Innerhalb der bestehenden `<Route path="clients/:clientId" element={<ClientShell />}>`-Gruppe:

```tsx
<Route path="checkins" element={<ClientCheckins />} />
```

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ClientCheckins.tsx frontend/src/components/ClientShell.tsx frontend/src/App.tsx
git commit -m "feat: add ClientCheckins review tab + nav entry + route"
```

---

### Task 14: Dashboard - Badge für offene Check-ins

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: `DashboardClientCard` um Badge erweitern**

In `frontend/src/pages/Dashboard.tsx`, `DashboardClientCard` anpassen:

```tsx
function DashboardClientCard({ client: c }: { client: Client }) {
  const age = ageFromBirthDate(c.birth_date);
  const metaLine = [age ? `${age} Jahre` : null, c.height_cm ? `${c.height_cm} cm` : null]
    .filter(Boolean)
    .join(" · ");

  return (
    <Link
      to={`/clients/${c.id}/timeline`}
      className="rounded-xl border border-white/5 bg-surface p-4 transition-colors hover:border-accent/40"
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-base font-semibold text-white">{c.name}</p>
        {c.pending_checkins_count > 0 && (
          <span className="shrink-0 rounded-full bg-amber-500/15 px-2 py-0.5 text-xs font-medium text-amber-400">
            {c.pending_checkins_count} offene{c.pending_checkins_count === 1 ? "r" : ""} Check-in
            {c.pending_checkins_count === 1 ? "" : "s"}
          </span>
        )}
      </div>
      <p className="mt-1 text-xs text-slate-500">{metaLine || "Keine Metriken hinterlegt"}</p>
      <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
        <span>{c.photo_count} Fotos</span>
        <span>
          {c.last_activity
            ? `Zuletzt: ${new Date(c.last_activity).toLocaleDateString("de-DE")}`
            : "Keine Fotos"}
        </span>
      </div>
    </Link>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat: show pending checkins badge on Dashboard client cards"
```

---

### Task 15: `Settings.tsx` - Magic-Link-Verwaltung, Coach-Notiz, Erinnerungs-Konfiguration

**Files:**
- Modify: `frontend/src/pages/Settings.tsx`

- [ ] **Step 1: Neuen Abschnitt oberhalb der bestehenden Posen-Verwaltung ergänzen**

In `frontend/src/pages/Settings.tsx`: Imports und State ergänzen, neuen Abschnitt vor dem bestehenden `<div className="rounded-xl border border-white/5 bg-surface p-4">` (Posen-Liste) einfügen.

```tsx
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import PageHeader from "../components/PageHeader";

export default function Settings() {
  const { clientId } = useParams<{ clientId: string }>();
  const clientIdNum = Number(clientId);
  const queryClient = useQueryClient();
  const [newPoseName, setNewPoseName] = useState("");
  const [editing, setEditing] = useState<Record<number, string>>({});

  const [copyFeedback, setCopyFeedback] = useState(false);
  const [coachNote, setCoachNote] = useState("");
  const [clientEmail, setClientEmail] = useState("");
  const [reminderDays, setReminderDays] = useState("");

  const clientQuery = useQuery({
    queryKey: ["clients", clientIdNum],
    queryFn: () => api.clients.get(clientIdNum),
  });

  useEffect(() => {
    if (!clientQuery.data) return;
    setCoachNote(clientQuery.data.coach_private_note ?? "");
    setClientEmail(clientQuery.data.email ?? "");
    setReminderDays(
      clientQuery.data.checkin_reminder_days != null ? String(clientQuery.data.checkin_reminder_days) : ""
    );
  }, [clientQuery.data]);

  const updateClientMutation = useMutation({
    mutationFn: () =>
      api.clients.update(clientIdNum, {
        coach_private_note: coachNote.trim() === "" ? null : coachNote,
        email: clientEmail.trim() === "" ? null : clientEmail.trim(),
        checkin_reminder_days: reminderDays.trim() === "" ? null : Number(reminderDays),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["clients", clientIdNum] }),
  });

  const regenerateTokenMutation = useMutation({
    mutationFn: () => api.clients.regenerateCheckinToken(clientIdNum),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["clients", clientIdNum] }),
  });

  const posesQuery = useQuery({
    queryKey: ["poses", clientIdNum],
    queryFn: () => api.poses.list(clientIdNum),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["poses", clientIdNum] });

  const createMutation = useMutation({
    mutationFn: (name: string) => api.poses.create(clientIdNum, name),
    onSuccess: () => {
      setNewPoseName("");
      invalidate();
    },
  });

  const renameMutation = useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) =>
      api.poses.update(clientIdNum, id, { name }),
    onSuccess: invalidate,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.poses.remove(clientIdNum, id),
    onSuccess: invalidate,
  });

  const poses = posesQuery.data ?? [];
  const MAX_POSES = 20;
  const checkinLink = clientQuery.data
    ? `${window.location.origin}/checkin/${clientQuery.data.checkin_token}`
    : "";

  return (
    <div className="max-w-xl space-y-6">
      <PageHeader title="Settings" />

      <div className="space-y-4 rounded-xl border border-white/5 bg-surface p-4">
        <div>
          <p className="text-sm font-medium text-white">Check-in-Link für den Klienten</p>
          <p className="mt-1 text-xs text-slate-500">
            Dieser Link ist dauerhaft gültig - der Klient kann ihn sich bookmarken und für jeden
            Check-in wiederverwenden.
          </p>
          <div className="mt-2 flex gap-2">
            <input
              readOnly
              value={checkinLink}
              className="flex-1 rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-xs text-slate-300"
            />
            <button
              onClick={() => {
                navigator.clipboard.writeText(checkinLink);
                setCopyFeedback(true);
                setTimeout(() => setCopyFeedback(false), 2000);
              }}
              className="rounded-lg border border-white/10 px-3 py-2 text-xs font-medium text-white hover:bg-white/5"
            >
              {copyFeedback ? "Kopiert!" : "Kopieren"}
            </button>
          </div>
          <button
            onClick={() => {
              if (confirm("Neuen Link generieren? Der alte Link funktioniert danach nicht mehr.")) {
                regenerateTokenMutation.mutate();
              }
            }}
            disabled={regenerateTokenMutation.isPending}
            className="mt-2 text-xs text-slate-500 hover:text-white disabled:opacity-50"
          >
            Link neu generieren
          </button>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            updateClientMutation.mutate();
          }}
          className="space-y-3 border-t border-white/5 pt-4"
        >
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            E-Mail des Klienten (für Erinnerungen)
            <input
              type="email"
              value={clientEmail}
              onChange={(e) => setClientEmail(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Erinnerung nach X Tagen ohne Check-in (leer = keine Erinnerung)
            <input
              type="number"
              min={1}
              value={reminderDays}
              onChange={(e) => setReminderDays(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Private Notiz (nur für dich sichtbar)
            <textarea
              value={coachNote}
              onChange={(e) => setCoachNote(e.target.value)}
              rows={3}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <button
            type="submit"
            disabled={updateClientMutation.isPending}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-50"
          >
            {updateClientMutation.isPending ? "Speichern…" : "Speichern"}
          </button>
        </form>
      </div>

      <div className="rounded-xl border border-white/5 bg-surface p-4">
        {/* ... bestehende Posen-Verwaltung unverändert ... */}
      </div>
    </div>
  );
}
```

Hinweis für den Implementierer: der Kommentar `{/* ... bestehende Posen-Verwaltung unverändert ... */}` ist ein Platzhalter für den bereits bestehenden JSX-Block (Posen-Liste + "Neue Pose"-Formular) aus der aktuellen Datei - dieser Block wird 1:1 übernommen, nur in das neue äußere Layout eingebettet (der neue Abschnitt kommt DAVOR, nicht anstelle davon).

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler.

- [ ] **Step 3: Manueller Check**

Run: `npm run dev`, öffne Settings eines Klienten, prüfe: Link wird angezeigt, "Kopieren" funktioniert, "Link neu generieren" fragt nach Bestätigung und ändert den Link, E-Mail/Erinnerungstage/Notiz lassen sich speichern und bleiben nach Reload erhalten.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Settings.tsx
git commit -m "feat: add magic-link management, reminder config, and coach note to Settings"
```

---

## Abschließende Verifikation

- [ ] Volle Backend-Suite: `cd backend && .venv/Scripts/python -m pytest -v` — alle grün.
- [ ] Frontend-Typecheck: `cd frontend && npx tsc --noEmit` — keine Fehler.
- [ ] Manueller Durchlauf: Als Coach einen Klienten anlegen → in Settings E-Mail + Erinnerungstage setzen, Check-in-Link kopieren → Link in neuem Tab (ausgeloggt) öffnen → Check-in mit Gewicht + Notiz + Foto einreichen → als Coach im Dashboard das "offene Check-ins"-Badge sehen → im Check-ins-Tab den Eintrag öffnen, Feedback-Text + Video-Link setzen, "Als geprüft markieren" klicken → im Klienten-Link erneut öffnen und das Feedback sehen.
- [ ] Bestätigen, dass `docs/superpowers/specs/2026-08-15-checkin-review-platform-design.md` vollständig abgedeckt ist (Magic-Link, Einreichung, Review-Queue, Feedback, Compliance-Anzeige, Coach-Notiz, beide E-Mail-Typen).
