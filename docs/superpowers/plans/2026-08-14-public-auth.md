# Public Auth (Stufe 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Öffentliche Registrierung (E-Mail+Passwort mit Verifizierung, Google OAuth), Passwort-Reset, Konto-Löschung und Datenexport (DSGVO) für BodyComp Tracker.

**Architecture:** Erweitert die bestehende Stufe-1-Architektur (FastAPI + SQLAlchemy + httpOnly-Session-Cookies) um `authlib` (Google OAuth) und `resend` (transaktionale E-Mails). Kein Wechsel auf externen Auth-Dienst.

**Tech Stack:** FastAPI, SQLAlchemy, authlib, resend (Python SDK), itsdangerous (bereits vorhanden), React + TypeScript + react-query.

---

## Part 0 — Vorab-Aufräumarbeiten

### Task 1: Migrations-Code entfernen

Die einmalige Stufe-1-Migration ist bereits erfolgreich gegen die echte Produktions-DB gelaufen und wird nie wieder gebraucht.

**Files:**
- Delete: `backend/app/core/migrate_to_multitenancy.py`
- Delete: `backend/app/core/migrate_legacy_unique_constraints.py`
- Delete: `backend/tests/test_migrate_to_multitenancy.py`
- Delete: `backend/tests/test_legacy_constraint_migration.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Entferne die Migrations-Aufrufe aus `main.py`**

Aktueller Inhalt von `backend/app/main.py`:
```python
"""
FastAPI Entry-Point.

Für den POC: erzeugt Tabellen direkt via Base.metadata.create_all
(kein Alembic-Migrationslauf nötig). Für die spätere Cloud-Version
sollte das durch echte Alembic-Migrationen ersetzt werden.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import Base, SessionLocal, engine  # noqa: F401 - SessionLocal wird von tests/conftest.py gepatcht
from app.core.migrate_legacy_unique_constraints import fix_legacy_unique_constraints
from app.core.migrate_to_multitenancy import migrate_to_multitenancy
from app.core.migrations import run_lightweight_migrations
from app.models import app_setting  # noqa: F401 - Import registriert Table bei create_all
from app.models import user  # noqa: F401 - Import registriert Table bei create_all
from app.models import client  # noqa: F401 - Import registriert Table bei create_all
from app.routers import auth, clients, comparisons, day_logs, photos, poses, settings as settings_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    run_lightweight_migrations(engine)
    fix_legacy_unique_constraints(engine)
    db = SessionLocal()
    try:
        migrate_to_multitenancy(
            db,
            email="basti.auer@outlook.com",
            password=settings.migration_seed_password,
            display_name="Basti",
        )
    finally:
        db.close()
    yield
```

Ersetze durch:
```python
"""
FastAPI Entry-Point.

Für den POC: erzeugt Tabellen direkt via Base.metadata.create_all
(kein Alembic-Migrationslauf nötig). Für die spätere Cloud-Version
sollte das durch echte Alembic-Migrationen ersetzt werden.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.database import Base, SessionLocal, engine  # noqa: F401 - SessionLocal wird von tests/conftest.py gepatcht
from app.core.migrations import run_lightweight_migrations
from app.models import app_setting  # noqa: F401 - Import registriert Table bei create_all
from app.models import user  # noqa: F401 - Import registriert Table bei create_all
from app.models import client  # noqa: F401 - Import registriert Table bei create_all
from app.routers import auth, clients, comparisons, day_logs, photos, poses, settings as settings_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    run_lightweight_migrations(engine)
    yield
```

(Der restliche Inhalt von `main.py` - CORS-Middleware, `/media`-Mount, `include_router`-Aufrufe, `/api/health` - bleibt unverändert. `settings`-Import fällt weg, da er nur noch für `migration_seed_password` gebraucht wurde - falls er anderswo in der Datei noch verwendet wird, behalte ihn.)

- [ ] **Step 2: Dateien löschen**

```bash
cd backend
rm app/core/migrate_to_multitenancy.py
rm app/core/migrate_legacy_unique_constraints.py
rm tests/test_migrate_to_multitenancy.py
rm tests/test_legacy_constraint_migration.py
```

- [ ] **Step 3: `migration_seed_password` aus `config.py` entfernen**

In `backend/app/core/config.py`, entferne diesen Block aus der `Settings`-Klasse:
```python
    # Startpasswort für den einmalig migrierten Coach-Account (siehe
    # core/migrate_to_multitenancy.py). NICHT im Repo im Klartext - wird
    # über backend/.env gesetzt (BODYCOMP_MIGRATION_SEED_PASSWORD), nicht
    # committed (siehe .gitignore).
    migration_seed_password: str = "changeme-set-in-dotenv"
```

- [ ] **Step 4: Volle Testsuite laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest -v`
Expected: alle bisherigen Tests außer den gelöschten laufen weiter durch, keine Fehler durch fehlende Imports.

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/app/core/config.py
git add -u backend/app/core/migrate_to_multitenancy.py backend/app/core/migrate_legacy_unique_constraints.py
git add -u backend/tests/test_migrate_to_multitenancy.py backend/tests/test_legacy_constraint_migration.py
git commit -m "chore: remove one-time Stufe-1-migration code (already run successfully in production)"
```

---

### Task 2: `Client.age` → `Client.birth_date`

**Files:**
- Modify: `backend/app/models/client.py`
- Modify: `backend/app/schemas/client.py`
- Modify: `backend/app/core/migrations.py`
- Modify: `backend/tests/test_clients_router.py`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: Update `app/models/client.py`**

Ersetze die `age`-Zeile:
```python
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
```
durch:
```python
    birth_date: Mapped[date_ | None] = mapped_column(Date, nullable=True)
```
(`Integer`-Import kann entfernt werden, falls sonst nirgends in der Datei genutzt - prüfen, ob `Integer` noch für `id` oder andere Spalten gebraucht wird, bevor der Import entfernt wird.)

- [ ] **Step 2: Update `app/schemas/client.py`**

In `ClientCreate`, `ClientUpdate`, `ClientOut`: ersetze jeweils `age: int | None = None` (bzw. ohne Default in `ClientOut`) durch `birth_date: date_ | None = None` (bzw. `birth_date: date_ | None` in `ClientOut`).

- [ ] **Step 3: Lightweight-Migration für bestehende Client-Zeilen**

In `backend/app/core/migrations.py`, füge zu `_PENDING_COLUMNS` hinzu:
```python
    ("clients", "birth_date", "DATE"),
```
(Die alte `age`-Spalte bleibt in der DB als verwaistes, ungenutztes Feld bestehen - SQLite kann Spalten nicht per `ALTER TABLE` löschen ohne Tabellen-Rebuild, und das lohnt sich hier nicht: die App liest/schreibt sie einfach nie wieder, kein Verhalten hängt daran.)

- [ ] **Step 4: Bestehenden Test anpassen**

In `backend/tests/test_clients_router.py`, in `test_create_and_list_clients`, ersetze:
```python
        json={"name": "Max Mustermann", "height_cm": 180, "age": 28, "gender": "männlich", "start_date": "2026-01-01"},
```
durch:
```python
        json={"name": "Max Mustermann", "height_cm": 180, "birth_date": "1998-01-01", "gender": "männlich", "start_date": "2026-01-01"},
```
und die zugehörige Assertion `assert created["height_cm"] == 180` bleibt, aber ergänze:
```python
    assert created["birth_date"] == "1998-01-01"
```

- [ ] **Step 5: Backend-Tests laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_clients_router.py -v`
Expected: alle grün.

- [ ] **Step 6: Frontend `types/index.ts` anpassen**

In `frontend/src/types/index.ts`, im `Client`-Interface, ersetze:
```typescript
  age: number | null;
```
durch:
```typescript
  birth_date: string | null; // ISO YYYY-MM-DD
```

- [ ] **Step 7: `Dashboard.tsx` anpassen**

In `frontend/src/pages/Dashboard.tsx`: ersetze den `age`-State und das zugehörige Formularfeld.

Ersetze:
```typescript
  const [age, setAge] = useState("");
```
durch:
```typescript
  const [birthDate, setBirthDate] = useState("");
```

Im `createMutation`-Payload, ersetze:
```typescript
        age: age.trim() === "" ? null : Number(age),
```
durch:
```typescript
        birth_date: birthDate.trim() === "" ? null : birthDate,
```

Im `onSuccess`-Reset, ersetze `setAge("");` durch `setBirthDate("");`.

Im Formular-JSX, ersetze den kompletten "Alter"-`<label>`-Block:
```tsx
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Alter
            <input
              type="number"
              value={age}
              onChange={(e) => setAge(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
```
durch:
```tsx
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Geburtsdatum
            <input
              type="date"
              value={birthDate}
              onChange={(e) => setBirthDate(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
```

Im Client-Karten-Rendering, ersetze:
```tsx
              {[c.age ? `${c.age} Jahre` : null, c.height_cm ? `${c.height_cm} cm` : null]
```
durch (berechnet das Alter aus `birth_date`, statt es direkt zu speichern):
```tsx
              {[
                c.birth_date
                  ? `${Math.floor((Date.now() - new Date(c.birth_date).getTime()) / (365.25 * 24 * 60 * 60 * 1000))} Jahre`
                  : null,
                c.height_cm ? `${c.height_cm} cm` : null,
              ]
```

- [ ] **Step 8: Frontend-Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler.

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/client.py backend/app/schemas/client.py backend/app/core/migrations.py backend/tests/test_clients_router.py frontend/src/types/index.ts frontend/src/pages/Dashboard.tsx
git commit -m "feat: replace Client.age with Client.birth_date"
```

---

## Part 1 — Backend: Datenmodell

### Task 3: `User`-Erweiterungen + `EmailToken`-Model

**Files:**
- Modify: `backend/app/models/user.py`
- Create: `backend/app/models/email_token.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/core/migrations.py`
- Test: `backend/tests/test_user_model_stage2.py`

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_user_model_stage2.py
from datetime import datetime, timedelta, timezone

from app.models.email_token import EmailToken, EmailTokenPurpose
from app.models.user import User


def test_user_can_be_created_without_password(db_session):
    """Google-only-Accounts haben kein Passwort."""
    user = User(email="google@example.com", display_name="Google User", google_id="google-sub-123")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    assert user.password_hash is None
    assert user.email_verified_at is None
    assert user.privacy_accepted_at is None
    assert user.sessions_invalidated_at is None


def test_user_google_id_is_unique(db_session):
    from sqlalchemy.exc import IntegrityError
    import pytest

    db_session.add(User(email="a@b.com", display_name="A", google_id="dup-sub"))
    db_session.commit()

    db_session.add(User(email="c@d.com", display_name="C", google_id="dup-sub"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_email_token_belongs_to_user_and_has_purpose(db_session):
    user = User(email="a@b.com", display_name="A", password_hash="x")
    db_session.add(user)
    db_session.flush()

    token = EmailToken(
        user_id=user.id,
        token_hash="abc123hash",
        purpose=EmailTokenPurpose.VERIFY_EMAIL,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db_session.add(token)
    db_session.commit()
    db_session.refresh(token)

    assert token.used_at is None
    assert token.purpose == EmailTokenPurpose.VERIFY_EMAIL


def test_email_token_deleted_when_user_deleted(db_session):
    user = User(email="a@b.com", display_name="A", password_hash="x")
    db_session.add(user)
    db_session.flush()
    db_session.add(EmailToken(
        user_id=user.id,
        token_hash="abc",
        purpose=EmailTokenPurpose.RESET_PASSWORD,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    ))
    db_session.commit()

    db_session.delete(user)
    db_session.commit()

    assert db_session.query(EmailToken).count() == 0
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_user_model_stage2.py -v`
Expected: FAIL - `ModuleNotFoundError: No module named 'app.models.email_token'` (und `google_id` existiert noch nicht auf `User`)

- [ ] **Step 3: `app/models/user.py` erweitern**

Ersetze den kompletten Inhalt von `backend/app/models/user.py`:
```python
"""
User = ein Account, der sich einloggt. Kann `single` (nur eigener
Fortschritt, kein Dashboard) oder `coach` (mehrere Kunden, Dashboard)
sein - siehe Design-Spec Abschnitt "Kontotyp". Jeder User bekommt bei
Anlage automatisch genau einen Client (siehe app/models/client.py),
unabhängig vom account_type.

Stufe 2 (Public Auth): password_hash ist jetzt nullable, da ein
rein über Google registrierter Account kein eigenes Passwort hat.
google_id verknüpft mit Googles OAuth-Konto (`sub`-Claim).
email_verified_at ist NULL, bis die E-Mail bestätigt wurde (Google-
Accounts sind sofort verifiziert). privacy_accepted_at ist der
Zustimmungs-Nachweis zur Datenschutzerklärung (DSGVO).
sessions_invalidated_at wird bei einem Passwort-Reset gesetzt, um
alle vorher ausgestellten Session-Cookies ungültig zu machen.
"""
import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AccountType(str, enum.Enum):
    SINGLE = "single"
    COACH = "coach"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_type: Mapped[AccountType] = mapped_column(
        Enum(AccountType), default=AccountType.SINGLE, nullable=False
    )
    google_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    privacy_accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sessions_invalidated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    clients: Mapped[list["Client"]] = relationship(  # noqa: F821
        back_populates="owner", cascade="all, delete-orphan"
    )
    email_tokens: Mapped[list["EmailToken"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} account_type={self.account_type}>"
```

- [ ] **Step 4: `app/models/email_token.py` erstellen**

```python
"""
EmailToken = ein einmal verwendbarer, zeitlich befristeter Nachweis für
einen per Mail verschickten Link (E-Mail-Bestätigung oder Passwort-Reset)
- siehe Design-Spec Abschnitt "Datenmodell". Der Link selbst ist ein
signierter itsdangerous-Token (wie Session-Cookies); hier landet nur der
GEHASHTE Token, damit ein DB-Leak keine gültigen Links preisgibt.
"""
import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class EmailTokenPurpose(str, enum.Enum):
    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"


class EmailToken(Base):
    __tablename__ = "email_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    purpose: Mapped[EmailTokenPurpose] = mapped_column(Enum(EmailTokenPurpose), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="email_tokens")  # noqa: F821

    def __repr__(self) -> str:
        return f"<EmailToken id={self.id} user_id={self.user_id} purpose={self.purpose}>"
```

- [ ] **Step 5: In `main.py` registrieren**

In `backend/app/main.py`, füge nach dem `client`-Import hinzu:
```python
from app.models import email_token  # noqa: F401 - Import registriert Table bei create_all
```

- [ ] **Step 6: Lightweight-Migration für bestehende `users`-Zeilen**

In `backend/app/core/migrations.py`, füge zu `_PENDING_COLUMNS` hinzu:
```python
    ("users", "google_id", "VARCHAR(255)"),
    ("users", "email_verified_at", "DATETIME"),
    ("users", "privacy_accepted_at", "DATETIME"),
    ("users", "sessions_invalidated_at", "DATETIME"),
```
(Die alte `password_hash NOT NULL`-Spalte bleibt in bestehenden DBs technisch NOT NULL bestehen - SQLite kann das per `ALTER TABLE` nicht lockern. Das ist unkritisch: der bereits migrierte Account aus Stufe 1 hat ohnehin ein Passwort gesetzt, und alle NEUEN Accounts landen über `create_all()` in einer frischen DB, wo die Spalte von Anfang an nullable ist. Betrifft nur bestehende Produktions-DBs mit Altdaten - dort ist ein Passwort immer vorhanden.)

Bestehende Nutzer bekommen `email_verified_at` initial NULL nachgetragen - das würde sie beim nächsten Login aussperren. Deshalb: direkt im Anschluss an die Spalten-Migration in `run_lightweight_migrations`, setze `email_verified_at` für alle Zeilen, die noch NULL sind UND ein Passwort haben (= migrierte Alt-Accounts, keine neuen Signups), auf `created_at` (sie waren ja schon "verifiziert" im Sinne von Stufe 1 - manuell angelegt). Füge dafür am Ende von `run_lightweight_migrations` (nach der bestehenden Spalten-Schleife, noch innerhalb desselben `with engine.begin() as conn:`-Blocks) hinzu:
```python
        if "users" in existing_tables:
            existing_user_columns = {col["name"] for col in inspector.get_columns("users")}
            if "email_verified_at" in existing_user_columns:
                conn.execute(text(
                    "UPDATE users SET email_verified_at = created_at "
                    "WHERE email_verified_at IS NULL AND password_hash IS NOT NULL"
                ))
```

- [ ] **Step 7: Tests laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_user_model_stage2.py -v`
Expected: `4 passed`

- [ ] **Step 8: Volle Suite laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest -v`
Expected: alle grün (bestehende Auth-Tests legen `User` ohne die neuen Felder an - die haben Defaults/sind nullable, sollte nicht brechen).

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/user.py backend/app/models/email_token.py backend/app/main.py backend/app/core/migrations.py backend/tests/test_user_model_stage2.py
git commit -m "feat: extend User for Stufe 2 (google_id, verification, privacy consent, session invalidation), add EmailToken model"
```

---

### Task 4: Dependencies installieren, Settings erweitern

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`

- [ ] **Step 1: Dependencies hinzufügen**

In `backend/requirements.txt`, füge hinzu:
```
authlib>=1.3.2
resend>=2.5.1
```

Run: `cd backend && .venv/Scripts/python -m pip install -r requirements.txt`

- [ ] **Step 2: Settings erweitern**

In `backend/app/core/config.py`, füge zur `Settings`-Klasse hinzu (nach `session_secret_key`):
```python
    # Google OAuth (siehe routers/auth_google.py). In Google Cloud Console
    # unter "APIs & Services > Credentials" anzulegen.
    google_client_id: str = ""
    google_client_secret: str = ""
    # Muss exakt der in der Google Cloud Console hinterlegten Redirect-URI
    # entsprechen. Lokal: http://localhost:8000/api/auth/google/callback
    google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"

    # Resend (transaktionaler E-Mail-Versand, siehe services/email.py).
    resend_api_key: str = ""
    # Absenderadresse - im Sandbox-Modus (keine verifizierte Domain) muss
    # das Resends Standard-Testadresse sein: onboarding@resend.dev
    email_from_address: str = "onboarding@resend.dev"

    # Basis-URL des Frontends, für Links in E-Mails (Bestätigung, Reset).
    frontend_base_url: str = "http://localhost:5173"
```

- [ ] **Step 3: `.env.example` erweitern**

Füge zu `backend/.env.example` hinzu:
```
BODYCOMP_GOOGLE_CLIENT_ID=change-me
BODYCOMP_GOOGLE_CLIENT_SECRET=change-me
BODYCOMP_GOOGLE_REDIRECT_URI=http://localhost:8000/api/auth/google/callback
BODYCOMP_RESEND_API_KEY=change-me
BODYCOMP_EMAIL_FROM_ADDRESS=onboarding@resend.dev
BODYCOMP_FRONTEND_BASE_URL=http://localhost:5173
```

- [ ] **Step 4: Import-Sanity-Check**

Run: `cd backend && .venv/Scripts/python -c "from app.core.config import settings; print(settings.google_client_id)"`
Expected: druckt einen leeren String, kein Fehler.

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt backend/app/core/config.py backend/.env.example
git commit -m "feat: add authlib/resend dependencies and Stufe-2 settings"
```

---

## Part 2 — Backend: E-Mail-Versand + Rate-Limiting (gemeinsam genutzte Bausteine)

### Task 5: E-Mail-Service (Resend)

**Files:**
- Create: `backend/app/services/email.py`
- Test: `backend/tests/test_email_service.py`

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_email_service.py
from unittest.mock import MagicMock, patch

from app.services.email import send_verification_email, send_password_reset_email


def test_send_verification_email_calls_resend_with_correct_recipient():
    with patch("app.services.email.resend.Emails.send") as mock_send:
        mock_send.return_value = {"id": "fake-id"}
        send_verification_email(to="user@example.com", verify_url="https://app.example.com/verify-email?token=abc")

    assert mock_send.call_count == 1
    call_kwargs = mock_send.call_args[0][0]
    assert call_kwargs["to"] == ["user@example.com"]
    assert "verify-email?token=abc" in call_kwargs["html"]


def test_send_password_reset_email_calls_resend_with_correct_recipient():
    with patch("app.services.email.resend.Emails.send") as mock_send:
        mock_send.return_value = {"id": "fake-id"}
        send_password_reset_email(to="user@example.com", reset_url="https://app.example.com/reset-password?token=xyz")

    assert mock_send.call_count == 1
    call_kwargs = mock_send.call_args[0][0]
    assert call_kwargs["to"] == ["user@example.com"]
    assert "reset-password?token=xyz" in call_kwargs["html"]
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_email_service.py -v`
Expected: FAIL - `ModuleNotFoundError: No module named 'app.services.email'`

- [ ] **Step 3: `app/services/email.py` schreiben**

```python
"""
Transaktionaler E-Mail-Versand über Resend - siehe Design-Spec Abschnitt
"E-Mail-Versand (Resend)". Läuft synchron im Request; bei einem
Resend-Fehler soll der Aufrufer die Exception sehen und dem Nutzer eine
ehrliche Fehlermeldung zeigen, statt einen stillen Fehlschlag zu haben.

Sandbox-Modus (keine verifizierte Domain, siehe Design-Spec): Mails gehen
nur an die eigene, bei Resend verifizierte Test-Adresse - das ist eine
Resend-seitige Einschränkung, keine hier im Code abgebildete.
"""
import resend

from app.core.config import settings

resend.api_key = settings.resend_api_key


def _base_email_html(title: str, body_html: str) -> str:
    return f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto; color: #0b0f14;">
      <h1 style="font-size: 20px;">BodyComp <span style="color: #0891b2;">Tracker</span></h1>
      <h2 style="font-size: 16px;">{title}</h2>
      {body_html}
    </div>
    """


def send_verification_email(*, to: str, verify_url: str) -> None:
    html = _base_email_html(
        "Bitte bestätige deine E-Mail-Adresse",
        f"""
        <p>Klicke auf den folgenden Link, um deine Registrierung abzuschließen:</p>
        <p><a href="{verify_url}">{verify_url}</a></p>
        <p style="color: #64748b; font-size: 13px;">Der Link ist 24 Stunden gültig.</p>
        """,
    )
    resend.Emails.send({
        "from": settings.email_from_address,
        "to": [to],
        "subject": "Bestätige deine E-Mail-Adresse - BodyComp Tracker",
        "html": html,
    })


def send_password_reset_email(*, to: str, reset_url: str) -> None:
    html = _base_email_html(
        "Passwort zurücksetzen",
        f"""
        <p>Klicke auf den folgenden Link, um ein neues Passwort zu setzen:</p>
        <p><a href="{reset_url}">{reset_url}</a></p>
        <p style="color: #64748b; font-size: 13px;">Der Link ist 1 Stunde gültig. Falls du das
        nicht warst, kannst du diese Mail ignorieren.</p>
        """,
    )
    resend.Emails.send({
        "from": settings.email_from_address,
        "to": [to],
        "subject": "Passwort zurücksetzen - BodyComp Tracker",
        "html": html,
    })
```

- [ ] **Step 4: Test laufen lassen, Erfolg bestätigen**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_email_service.py -v`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/email.py backend/tests/test_email_service.py
git commit -m "feat: add Resend email service for verification and password reset mails"
```

---

### Task 6: Rate-Limiting-Dependency

**Files:**
- Create: `backend/app/core/rate_limit.py`
- Test: `backend/tests/test_rate_limit.py`

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_rate_limit.py
import pytest
from fastapi import FastAPI, Depends, HTTPException
from fastapi.testclient import TestClient

from app.core.rate_limit import RateLimiter


def _make_test_app():
    app = FastAPI()
    limiter = RateLimiter(max_requests=3, window_seconds=3600)

    @app.post("/limited")
    def limited_endpoint(_=Depends(limiter)):
        return {"ok": True}

    return app, limiter


def test_allows_requests_under_the_limit():
    app, _ = _make_test_app()
    client = TestClient(app)
    for _ in range(3):
        response = client.post("/limited")
        assert response.status_code == 200


def test_blocks_requests_over_the_limit():
    app, _ = _make_test_app()
    client = TestClient(app)
    for _ in range(3):
        client.post("/limited")
    response = client.post("/limited")
    assert response.status_code == 429


def test_limits_are_tracked_per_ip_independently():
    app, limiter = _make_test_app()
    client = TestClient(app)
    for _ in range(3):
        client.post("/limited", headers={"X-Forwarded-For": "1.1.1.1"})
    # andere IP darf noch
    response = client.post("/limited", headers={"X-Forwarded-For": "2.2.2.2"})
    assert response.status_code == 200
    # erste IP bleibt blockiert
    response = client.post("/limited", headers={"X-Forwarded-For": "1.1.1.1"})
    assert response.status_code == 429
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_rate_limit.py -v`
Expected: FAIL - `ModuleNotFoundError: No module named 'app.core.rate_limit'`

- [ ] **Step 3: `app/core/rate_limit.py` schreiben**

```python
"""
Einfaches In-Memory-Rate-Limiting pro IP-Adresse - siehe Design-Spec
Abschnitt "Rate-Limiting". Sliding-Window-Zähler im Prozessspeicher,
reicht für den aktuellen Single-Process-Betrieb.

Offener Punkt für Stufe 3 (siehe Design-Spec): bei Wechsel auf
Mehrprozess-/Mehrserver-Hosting muss das auf einen gemeinsamen Store
(Redis) wechseln - In-Memory funktioniert nur pro Einzelprozess.
"""
import time
from collections import defaultdict

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self, *, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    def __call__(self, request: Request) -> None:
        ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
        now = time.monotonic()
        cutoff = now - self.window_seconds

        hits = self._hits[ip]
        hits[:] = [t for t in hits if t > cutoff]

        if len(hits) >= self.max_requests:
            raise HTTPException(429, "Zu viele Versuche - bitte später erneut probieren.")

        hits.append(now)
```

- [ ] **Step 4: Test laufen lassen, Erfolg bestätigen**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_rate_limit.py -v`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/rate_limit.py backend/tests/test_rate_limit.py
git commit -m "feat: add in-memory per-IP rate limiter"
```

---

## Part 3 — Backend: Signup + E-Mail-Verifizierung

### Task 7: Token-Helfer (signiert + gehasht)

**Files:**
- Modify: `backend/app/services/auth.py`
- Test: `backend/tests/test_auth_service.py` (erweitern)

- [ ] **Step 1: Failing test**

Füge zu `backend/tests/test_auth_service.py` hinzu:
```python
from app.services.auth import create_email_token, hash_email_token, verify_email_token_signature


def test_create_email_token_is_verifiable():
    token = create_email_token(user_id=42, purpose="verify_email")
    payload = verify_email_token_signature(token, max_age_seconds=3600)
    assert payload == {"user_id": 42, "purpose": "verify_email"}


def test_verify_email_token_signature_rejects_tampered_token():
    token = create_email_token(user_id=42, purpose="verify_email")
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
    assert verify_email_token_signature(tampered, max_age_seconds=3600) is None


def test_verify_email_token_signature_rejects_expired_token():
    token = create_email_token(user_id=42, purpose="verify_email")
    assert verify_email_token_signature(token, max_age_seconds=-1) is None


def test_hash_email_token_is_deterministic_and_not_reversible():
    token = "some-raw-token-value"
    h1 = hash_email_token(token)
    h2 = hash_email_token(token)
    assert h1 == h2
    assert h1 != token
    assert len(h1) == 64  # sha256 hex digest
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_auth_service.py -v`
Expected: FAIL - `ImportError: cannot import name 'create_email_token'`

- [ ] **Step 3: `app/services/auth.py` erweitern**

Füge am Ende von `backend/app/services/auth.py` hinzu:
```python
import hashlib

_email_token_serializer = URLSafeTimedSerializer(settings.session_secret_key, salt="email-token")


def create_email_token(*, user_id: int, purpose: str) -> str:
    """Erzeugt einen signierten Token für E-Mail-Bestätigung/Passwort-
    Reset-Links. Der Aufrufer speichert `hash_email_token(token)` in der
    DB (siehe EmailToken.token_hash), NICHT den Token selbst."""
    return _email_token_serializer.dumps({"user_id": user_id, "purpose": purpose})


def verify_email_token_signature(token: str, *, max_age_seconds: int) -> dict | None:
    """Prüft nur Signatur + Ablauf des itsdangerous-Tokens - sagt NICHTS
    darüber aus, ob der zugehörige EmailToken in der DB noch existiert
    oder schon benutzt wurde (das prüft der Aufrufer separat gegen
    token_hash/used_at)."""
    try:
        return _email_token_serializer.loads(token, max_age=max_age_seconds)
    except BadSignature:
        return None


def hash_email_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Test laufen lassen, Erfolg bestätigen**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_auth_service.py -v`
Expected: alle grün (bestehende + 4 neue Tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/auth.py backend/tests/test_auth_service.py
git commit -m "feat: add signed+hashed token helpers for email verification/password reset"
```

---

### Task 8: Signup-Endpoint

**Files:**
- Create: `backend/app/schemas/signup.py`
- Modify: `backend/app/routers/auth.py`
- Test: `backend/tests/test_signup.py`

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_signup.py
from unittest.mock import patch

from app.models.email_token import EmailToken, EmailTokenPurpose
from app.models.user import User


def test_signup_creates_unverified_user_and_sends_email(client, db_session):
    with patch("app.routers.auth.send_verification_email") as mock_send:
        response = client.post(
            "/api/auth/signup",
            json={
                "email": "new@example.com",
                "password": "SuperSecret123!",
                "display_name": "New User",
                "privacy_accepted": True,
            },
        )
    assert response.status_code == 201
    assert mock_send.call_count == 1

    user = db_session.query(User).filter(User.email == "new@example.com").first()
    assert user is not None
    assert user.email_verified_at is None
    assert user.privacy_accepted_at is not None

    token_row = db_session.query(EmailToken).filter(EmailToken.user_id == user.id).first()
    assert token_row.purpose == EmailTokenPurpose.VERIFY_EMAIL
    assert token_row.used_at is None


def test_signup_without_privacy_consent_is_rejected(client, db_session):
    response = client.post(
        "/api/auth/signup",
        json={
            "email": "new@example.com",
            "password": "SuperSecret123!",
            "display_name": "New User",
            "privacy_accepted": False,
        },
    )
    assert response.status_code == 422


def test_signup_with_duplicate_email_fails(client, db_session):
    with patch("app.routers.auth.send_verification_email"):
        client.post(
            "/api/auth/signup",
            json={"email": "dup@example.com", "password": "SuperSecret123!", "display_name": "A", "privacy_accepted": True},
        )
        response = client.post(
            "/api/auth/signup",
            json={"email": "dup@example.com", "password": "AnotherPass123!", "display_name": "B", "privacy_accepted": True},
        )
    assert response.status_code == 409


def test_signup_rejects_short_password(client, db_session):
    response = client.post(
        "/api/auth/signup",
        json={"email": "new@example.com", "password": "short", "display_name": "New User", "privacy_accepted": True},
    )
    assert response.status_code == 422


def test_login_before_verification_is_rejected(client, db_session):
    with patch("app.routers.auth.send_verification_email"):
        client.post(
            "/api/auth/signup",
            json={"email": "unverified@example.com", "password": "SuperSecret123!", "display_name": "A", "privacy_accepted": True},
        )
    response = client.post(
        "/api/auth/login", json={"email": "unverified@example.com", "password": "SuperSecret123!"}
    )
    assert response.status_code == 403
    assert "best" in response.json()["detail"].lower()  # "bestätige" o.ä.
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_signup.py -v`
Expected: FAIL - 404 auf `/api/auth/signup` (Route existiert noch nicht)

- [ ] **Step 3: `app/schemas/signup.py` schreiben**

```python
from pydantic import BaseModel, EmailStr, Field, field_validator


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    display_name: str = Field(min_length=1, max_length=100)
    privacy_accepted: bool

    @field_validator("privacy_accepted")
    @classmethod
    def must_accept_privacy(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Datenschutzerklärung muss akzeptiert werden")
        return v


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=200)
```

- [ ] **Step 4: `app/routers/auth.py` um Signup/Verify erweitern**

Füge die Imports oben in `backend/app/routers/auth.py` hinzu (ergänzend zu den bestehenden):
```python
from datetime import datetime, timezone

from app.core.rate_limit import RateLimiter
from app.models.email_token import EmailToken, EmailTokenPurpose
from app.schemas.signup import ForgotPasswordRequest, ResetPasswordRequest, SignupRequest
from app.services.account import create_account
from app.services.auth import create_email_token, hash_email_token, verify_email_token_signature
from app.services.email import send_password_reset_email, send_verification_email
from app.core.config import settings
```

Füge nach dem `router = APIRouter(...)`-Aufruf die Rate-Limiter-Instanzen hinzu:
```python
signup_rate_limit = RateLimiter(max_requests=5, window_seconds=3600)
login_rate_limit = RateLimiter(max_requests=10, window_seconds=3600)
forgot_password_rate_limit = RateLimiter(max_requests=5, window_seconds=3600)
resend_verification_rate_limit = RateLimiter(max_requests=5, window_seconds=3600)
```

Füge `Depends(login_rate_limit)` als neuen Parameter zum bestehenden `login`-Endpunkt hinzu, und erweitere ihn um die Verifizierungs-Prüfung. Ersetze die bestehende `login`-Funktion:
```python
@router.post("/login", response_model=UserOut)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(login_rate_limit),
):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "E-Mail oder Passwort falsch")
    if user.email_verified_at is None:
        raise HTTPException(403, "Bitte bestätige zuerst deine E-Mail-Adresse")

    token = create_session_token(user.id)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=True,
    )
    return user
```

Füge die neuen Endpunkte am Ende der Datei hinzu:
```python
@router.post("/signup", response_model=UserOut, status_code=201)
def signup(
    payload: SignupRequest,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(signup_rate_limit),
):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(409, "E-Mail-Adresse ist bereits registriert")

    user = create_account(
        db, email=payload.email, password=payload.password, display_name=payload.display_name
    )
    user.privacy_accepted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    raw_token = create_email_token(user_id=user.id, purpose=EmailTokenPurpose.VERIFY_EMAIL.value)
    db.add(EmailToken(
        user_id=user.id,
        token_hash=hash_email_token(raw_token),
        purpose=EmailTokenPurpose.VERIFY_EMAIL,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    ))
    db.commit()

    verify_url = f"{settings.frontend_base_url}/verify-email?token={raw_token}"
    send_verification_email(to=user.email, verify_url=verify_url)

    return user


@router.get("/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    payload = verify_email_token_signature(token, max_age_seconds=60 * 60 * 24)
    if payload is None or payload.get("purpose") != EmailTokenPurpose.VERIFY_EMAIL.value:
        raise HTTPException(400, "Link ist ungültig oder abgelaufen")

    token_row = (
        db.query(EmailToken)
        .filter(
            EmailToken.user_id == payload["user_id"],
            EmailToken.token_hash == hash_email_token(token),
            EmailToken.purpose == EmailTokenPurpose.VERIFY_EMAIL,
            EmailToken.used_at.is_(None),
        )
        .first()
    )
    if token_row is None:
        raise HTTPException(400, "Link ist ungültig, abgelaufen oder bereits verwendet")

    user = db.get(User, payload["user_id"])
    user.email_verified_at = datetime.now(timezone.utc)
    token_row.used_at = datetime.now(timezone.utc)
    db.commit()
    return {"verified": True}


@router.post("/resend-verification", status_code=204)
def resend_verification(
    payload: ForgotPasswordRequest,  # gleiche Shape ({email}), wiederverwendet
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(resend_verification_rate_limit),
):
    user = db.query(User).filter(User.email == payload.email).first()
    if user is not None and user.email_verified_at is None:
        raw_token = create_email_token(user_id=user.id, purpose=EmailTokenPurpose.VERIFY_EMAIL.value)
        db.add(EmailToken(
            user_id=user.id,
            token_hash=hash_email_token(raw_token),
            purpose=EmailTokenPurpose.VERIFY_EMAIL,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        ))
        db.commit()
        verify_url = f"{settings.frontend_base_url}/verify-email?token={raw_token}"
        send_verification_email(to=user.email, verify_url=verify_url)
    # immer 204, unabhängig davon ob der Account existiert (kein Enumeration-Leak)
```

Ergänze `from datetime import timedelta` im `datetime`-Import ganz oben (`from datetime import datetime, timedelta, timezone`).

- [ ] **Step 5: Test laufen lassen, Erfolg bestätigen**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_signup.py -v`
Expected: `5 passed`

- [ ] **Step 6: Volle Suite laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest -v`
Expected: alle grün (prüfe insbesondere, dass bestehende Login-Tests aus `test_auth_router.py` weiterhin funktionieren - die legen `User` OHNE `email_verified_at` an, was jetzt zu 403 statt 200 führen würde; falls das bricht, siehe Step 7).

- [ ] **Step 7: Bestehenden Test-Helper reparieren, falls nötig**

Falls Step 6 zeigt, dass `test_auth_router.py`s `_make_user`-Helper jetzt fehlschlägt (weil `email_verified_at` NULL ist und `login` jetzt 403 statt 200 liefert): öffne `backend/tests/test_auth_router.py`, finde `_make_user`, und setze dort explizit `email_verified_at`:
```python
def _make_user(db_session, email="basti@example.com", password="Grindcore123!"):
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name="Basti",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.commit()
    return user
```
(Füge `from datetime import datetime, timezone` oben in der Datei hinzu, falls noch nicht vorhanden.) Führe danach die volle Suite erneut aus, um zu bestätigen, dass alles grün ist.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/signup.py backend/app/routers/auth.py backend/tests/test_signup.py
git add -u backend/tests/test_auth_router.py
git commit -m "feat: add signup + email verification endpoints, gate login on verified email"
```

---

## Part 4 — Backend: Google OAuth

### Task 9: Google-OAuth-Login/Callback

**Files:**
- Modify: `backend/app/routers/auth.py`
- Test: `backend/tests/test_google_oauth.py`

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_google_oauth.py
from unittest.mock import AsyncMock, patch

from app.models.user import AccountType, User
from app.services.auth import hash_password


def _fake_google_userinfo(sub="google-sub-123", email="google@example.com", name="Google User"):
    return {"sub": sub, "email": email, "email_verified": True, "name": name}


def test_google_callback_creates_new_user(client, db_session):
    with patch("app.routers.auth.oauth.google.authorize_access_token", new_callable=AsyncMock) as mock_token:
        mock_token.return_value = {"userinfo": _fake_google_userinfo()}
        response = client.get("/api/auth/google/callback", follow_redirects=False)

    assert response.status_code in (302, 307)
    user = db_session.query(User).filter(User.google_id == "google-sub-123").first()
    assert user is not None
    assert user.email == "google@example.com"
    assert user.display_name == "Google User"
    assert user.password_hash is None
    assert user.email_verified_at is not None
    assert user.privacy_accepted_at is not None
    assert "session" in response.cookies


def test_google_callback_logs_in_existing_google_user(client, db_session):
    existing = User(
        email="google@example.com",
        display_name="Google User",
        google_id="google-sub-123",
        email_verified_at=None,
    )
    from datetime import datetime, timezone
    existing.email_verified_at = datetime.now(timezone.utc)
    db_session.add(existing)
    db_session.commit()

    with patch("app.routers.auth.oauth.google.authorize_access_token", new_callable=AsyncMock) as mock_token:
        mock_token.return_value = {"userinfo": _fake_google_userinfo()}
        response = client.get("/api/auth/google/callback", follow_redirects=False)

    assert "session" in response.cookies
    assert db_session.query(User).count() == 1  # kein Duplikat


def test_google_callback_links_to_existing_email_password_account(client, db_session):
    from datetime import datetime, timezone
    existing = User(
        email="google@example.com",
        display_name="Existing",
        password_hash=hash_password("Whatever123!"),
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(existing)
    db_session.commit()
    existing_id = existing.id

    with patch("app.routers.auth.oauth.google.authorize_access_token", new_callable=AsyncMock) as mock_token:
        mock_token.return_value = {"userinfo": _fake_google_userinfo()}
        response = client.get("/api/auth/google/callback", follow_redirects=False)

    assert "session" in response.cookies
    db_session.refresh(existing)
    assert existing.google_id == "google-sub-123"
    assert db_session.query(User).count() == 1
    assert existing.id == existing_id
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_google_oauth.py -v`
Expected: FAIL - 404 auf `/api/auth/google/callback`

- [ ] **Step 3: OAuth-Client + Endpunkte in `app/routers/auth.py`**

Füge ganz oben in `backend/app/routers/auth.py` (nach den bestehenden Imports) hinzu:
```python
from authlib.integrations.starlette_client import OAuth
from fastapi.responses import RedirectResponse

oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)
```

Füge die Endpunkte am Ende der Datei hinzu:
```python
@router.get("/google/login")
async def google_login(request: Request):
    redirect_uri = settings.google_redirect_uri
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    token = await oauth.google.authorize_access_token(request)
    userinfo = token["userinfo"]
    google_sub = userinfo["sub"]
    email = userinfo["email"]
    name = userinfo.get("name") or email

    user = db.query(User).filter(User.google_id == google_sub).first()
    if user is None:
        user = db.query(User).filter(User.email == email).first()
        if user is not None:
            # bestehender E-Mail+Passwort-Account - automatisch verknüpfen
            user.google_id = google_sub
        else:
            user = create_account(db, email=email, password=None, display_name=name)
            user.google_id = google_sub
            user.privacy_accepted_at = datetime.now(timezone.utc)
        user.email_verified_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)

    session_token = create_session_token(user.id)
    response = RedirectResponse(url=f"{settings.frontend_base_url}/")
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=True,
    )
    return response
```

Füge `from fastapi import Request` zum bestehenden `fastapi`-Import hinzu (ergänze `Request` zur bestehenden `from fastapi import APIRouter, Cookie, Depends, HTTPException, Response`-Zeile).

- [ ] **Step 4: `create_account` um optionales Passwort erweitern**

`create_account` in `backend/app/services/account.py` erwartet aktuell ein Pflicht-`password: str`. Google-Accounts haben keins. Ersetze die Funktionssignatur und den Body:

```python
def create_account(
    db: Session,
    *,
    email: str,
    password: str | None,
    display_name: str,
    account_type: AccountType = AccountType.SINGLE,
) -> User:
    user = User(
        email=email,
        password_hash=hash_password(password) if password is not None else None,
        display_name=display_name,
        account_type=account_type,
    )
    db.add(user)
    db.flush()  # user.id wird gebraucht, bevor der Client angelegt wird

    db.add(Client(owner_id=user.id, name=display_name))
    db.commit()
    db.refresh(user)
    return user
```

- [ ] **Step 5: Test laufen lassen, Erfolg bestätigen**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_google_oauth.py -v`
Expected: `3 passed`

- [ ] **Step 6: Volle Suite laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest -v`
Expected: alle grün.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/auth.py backend/app/services/account.py backend/tests/test_google_oauth.py
git commit -m "feat: add Google OAuth login/callback with account auto-linking"
```

---

## Part 5 — Backend: Passwort-Reset

### Task 10: Forgot-Password / Reset-Password

**Files:**
- Modify: `backend/app/routers/auth.py`
- Modify: `backend/app/routers/auth.py` (`get_current_user`)
- Test: `backend/tests/test_password_reset.py`

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_password_reset.py
from datetime import datetime, timezone
from unittest.mock import patch

from app.models.email_token import EmailToken, EmailTokenPurpose
from app.models.user import User
from app.services.auth import create_email_token, hash_email_token, hash_password, verify_password


def _make_verified_user(db_session, email="basti@example.com", password="OldPass123!"):
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name="Basti",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_forgot_password_sends_email_for_existing_user(client, db_session):
    _make_verified_user(db_session)
    with patch("app.routers.auth.send_password_reset_email") as mock_send:
        response = client.post("/api/auth/forgot-password", json={"email": "basti@example.com"})
    assert response.status_code == 204
    assert mock_send.call_count == 1


def test_forgot_password_is_silent_for_unknown_email(client, db_session):
    with patch("app.routers.auth.send_password_reset_email") as mock_send:
        response = client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
    assert response.status_code == 204
    assert mock_send.call_count == 0


def test_forgot_password_is_silent_for_google_only_account(client, db_session):
    google_user = User(
        email="google@example.com", display_name="G", google_id="sub-1",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(google_user)
    db_session.commit()

    with patch("app.routers.auth.send_password_reset_email") as mock_send:
        response = client.post("/api/auth/forgot-password", json={"email": "google@example.com"})
    assert response.status_code == 204
    assert mock_send.call_count == 0


def test_reset_password_with_valid_token_changes_password_and_invalidates_sessions(client, db_session):
    user = _make_verified_user(db_session)
    raw_token = create_email_token(user_id=user.id, purpose=EmailTokenPurpose.RESET_PASSWORD.value)
    db_session.add(EmailToken(
        user_id=user.id,
        token_hash=hash_email_token(raw_token),
        purpose=EmailTokenPurpose.RESET_PASSWORD,
        expires_at=datetime.now(timezone.utc).replace(year=2030),
    ))
    db_session.commit()

    response = client.post(
        "/api/auth/reset-password", json={"token": raw_token, "new_password": "NewPass456!"}
    )
    assert response.status_code == 204

    db_session.refresh(user)
    assert verify_password("NewPass456!", user.password_hash)
    assert user.sessions_invalidated_at is not None


def test_reset_password_with_used_token_fails(client, db_session):
    user = _make_verified_user(db_session)
    raw_token = create_email_token(user_id=user.id, purpose=EmailTokenPurpose.RESET_PASSWORD.value)
    db_session.add(EmailToken(
        user_id=user.id,
        token_hash=hash_email_token(raw_token),
        purpose=EmailTokenPurpose.RESET_PASSWORD,
        expires_at=datetime.now(timezone.utc).replace(year=2030),
        used_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    response = client.post(
        "/api/auth/reset-password", json={"token": raw_token, "new_password": "NewPass456!"}
    )
    assert response.status_code == 400


def test_old_session_rejected_after_password_reset(client, db_session):
    user = _make_verified_user(db_session)
    login_resp = client.post("/api/auth/login", json={"email": "basti@example.com", "password": "OldPass123!"})
    assert login_resp.status_code == 200

    raw_token = create_email_token(user_id=user.id, purpose=EmailTokenPurpose.RESET_PASSWORD.value)
    db_session.add(EmailToken(
        user_id=user.id,
        token_hash=hash_email_token(raw_token),
        purpose=EmailTokenPurpose.RESET_PASSWORD,
        expires_at=datetime.now(timezone.utc).replace(year=2030),
    ))
    db_session.commit()
    client.post("/api/auth/reset-password", json={"token": raw_token, "new_password": "NewPass456!"})

    # altes Session-Cookie (vom Login vor dem Reset) darf jetzt nicht mehr gelten
    me_response = client.get("/api/auth/me")
    assert me_response.status_code == 401
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_password_reset.py -v`
Expected: FAIL - 404 auf `/api/auth/forgot-password`

- [ ] **Step 3: Endpunkte + `get_current_user`-Erweiterung in `app/routers/auth.py`**

Füge die Endpunkte am Ende der Datei hinzu:
```python
@router.post("/forgot-password", status_code=204)
def forgot_password(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(forgot_password_rate_limit),
):
    user = db.query(User).filter(User.email == payload.email).first()
    if user is not None and user.password_hash is not None:
        raw_token = create_email_token(user_id=user.id, purpose=EmailTokenPurpose.RESET_PASSWORD.value)
        db.add(EmailToken(
            user_id=user.id,
            token_hash=hash_email_token(raw_token),
            purpose=EmailTokenPurpose.RESET_PASSWORD,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ))
        db.commit()
        reset_url = f"{settings.frontend_base_url}/reset-password?token={raw_token}"
        send_password_reset_email(to=user.email, reset_url=reset_url)
    # immer 204 - kein Enumeration-Leak, egal ob Account existiert/Passwort hat


@router.post("/reset-password", status_code=204)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    token_payload = verify_email_token_signature(payload.token, max_age_seconds=60 * 60)
    if token_payload is None or token_payload.get("purpose") != EmailTokenPurpose.RESET_PASSWORD.value:
        raise HTTPException(400, "Link ist ungültig oder abgelaufen")

    token_row = (
        db.query(EmailToken)
        .filter(
            EmailToken.user_id == token_payload["user_id"],
            EmailToken.token_hash == hash_email_token(payload.token),
            EmailToken.purpose == EmailTokenPurpose.RESET_PASSWORD,
            EmailToken.used_at.is_(None),
        )
        .first()
    )
    if token_row is None:
        raise HTTPException(400, "Link ist ungültig, abgelaufen oder bereits verwendet")

    user = db.get(User, token_payload["user_id"])
    user.password_hash = hash_password(payload.new_password)
    user.sessions_invalidated_at = datetime.now(timezone.utc)
    token_row.used_at = datetime.now(timezone.utc)
    db.commit()
```

Ersetze die bestehende `get_current_user`-Funktion, um `sessions_invalidated_at` zu prüfen. Der Session-Token muss dafür wissen, WANN er ausgestellt wurde - `create_session_token` in `services/auth.py` speichert bisher nur `user_id`. Erweitere dort:

In `backend/app/services/auth.py`, ersetze:
```python
def create_session_token(user_id: int) -> str:
    return _serializer.dumps({"user_id": user_id})
```
durch:
```python
def create_session_token(user_id: int) -> str:
    return _serializer.dumps({"user_id": user_id, "issued_at": datetime.now(timezone.utc).isoformat()})
```
(Füge `from datetime import datetime, timezone` zum Import-Block oben in `services/auth.py` hinzu.)

Dann in `backend/app/routers/auth.py`, ersetze `get_current_user`:
```python
def get_current_user(
    session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI-Dependency: liest das Session-Cookie, validiert Signatur +
    Ablauf, lädt den User, prüft dass die Session nicht durch einen
    Passwort-Reset invalidiert wurde. Wirft 401, wenn irgendwas davon
    fehlschlägt."""
    if session is None:
        raise HTTPException(401, "Nicht eingeloggt")
    payload = verify_session_token(session)
    if payload is None:
        raise HTTPException(401, "Nicht eingeloggt")
    user = db.get(User, payload["user_id"])
    if user is None:
        raise HTTPException(401, "Nicht eingeloggt")
    if user.sessions_invalidated_at is not None:
        issued_at = datetime.fromisoformat(payload["issued_at"])
        if issued_at.tzinfo is None:
            issued_at = issued_at.replace(tzinfo=timezone.utc)
        invalidated_at = user.sessions_invalidated_at
        if invalidated_at.tzinfo is None:
            invalidated_at = invalidated_at.replace(tzinfo=timezone.utc)
        if issued_at < invalidated_at:
            raise HTTPException(401, "Nicht eingeloggt")
    return user
```

`verify_session_token` in `services/auth.py` gibt aktuell nur die `user_id` (int) zurück, nicht das ganze Payload-Dict. Passe es an:
```python
def verify_session_token(token: str) -> dict | None:
    """Gibt das Token-Payload (user_id, issued_at) zurück, wenn die
    Signatur gültig und das Cookie nicht abgelaufen ist - sonst None
    (nie eine Exception nach außen)."""
    try:
        return _serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
    except BadSignature:
        return None
```

**Wichtig:** `login`, `google_callback` in `routers/auth.py` rufen `create_session_token` unverändert auf (Signatur bleibt gleich) - kein Anpassungsbedarf dort. Nur `get_current_user`s Nutzung von `verify_session_token`s Rückgabewert ändert sich (jetzt ein Dict statt eines Int).

- [ ] **Step 4: Test laufen lassen, Erfolg bestätigen**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_password_reset.py -v`
Expected: `6 passed`

- [ ] **Step 5: Volle Suite laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest -v`
Expected: alle grün. Falls `test_auth_service.py`s bestehender `verify_session_token`-Test (aus Stufe 1, prüft direkten Rückgabewert) jetzt fehlschlägt, weil er einen `int` statt `dict` erwartet: öffne `backend/tests/test_auth_service.py`, finde den Test, der `verify_session_token` direkt aufruft, und passe die Assertion an das neue Dict-Format an (`result["user_id"]` statt `result`).

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/auth.py backend/app/services/auth.py
git add -u backend/tests/test_auth_service.py
git commit -m "feat: add password reset flow with session invalidation"
```

---

## Part 6 — Backend: DSGVO (Löschung, Export)

### Task 11: Konto-Löschung + Datenexport

**Files:**
- Modify: `backend/app/routers/auth.py`
- Test: `backend/tests/test_account_deletion_export.py`

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_account_deletion_export.py
from datetime import datetime, timezone

from app.models.client import Client
from app.models.user import User
from app.services.auth import hash_password


def _login_as(client, db_session, email="basti@example.com", password="Pass123456!"):
    user = User(
        email=email, password_hash=hash_password(password), display_name="Basti",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.commit()
    client.post("/api/auth/login", json={"email": email, "password": password})
    return user


def test_delete_account_requires_correct_password(client, db_session):
    _login_as(client, db_session)
    response = client.request("DELETE", "/api/auth/me", json={"password": "wrong"})
    assert response.status_code == 401


def test_delete_account_removes_user_and_clients(client, db_session):
    user = _login_as(client, db_session)
    user_id = user.id

    response = client.request("DELETE", "/api/auth/me", json={"password": "Pass123456!"})
    assert response.status_code == 204

    assert db_session.query(User).filter(User.id == user_id).first() is None
    assert db_session.query(Client).filter(Client.owner_id == user_id).count() == 0

    me_response = client.get("/api/auth/me")
    assert me_response.status_code == 401


def test_delete_google_only_account_without_password(client, db_session):
    google_user = User(
        email="google@example.com", display_name="G", google_id="sub-1",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(google_user)
    db_session.commit()

    from app.services.auth import create_session_token
    token = create_session_token(google_user.id)
    client.cookies.set("session", token)

    response = client.request("DELETE", "/api/auth/me", json={})
    assert response.status_code == 204
    assert db_session.query(User).filter(User.id == google_user.id).first() is None


def test_export_returns_user_and_client_data(client, db_session):
    _login_as(client, db_session)
    response = client.get("/api/auth/me/export")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "basti@example.com"
    assert len(body["clients"]) == 1
    assert body["clients"][0]["name"] == "Basti"
    assert "password_hash" not in body
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_account_deletion_export.py -v`
Expected: FAIL - 405/404 auf `DELETE /api/auth/me` und `GET /api/auth/me/export`

- [ ] **Step 3: Endpunkte in `app/routers/auth.py`**

Füge Imports hinzu (oben in der Datei, ergänzend):
```python
import shutil

from pydantic import BaseModel

from app.core.config import settings as app_settings
```

(Hinweis: `settings` ist in dieser Datei bereits importiert als `from app.core.config import settings` - falls das schon existiert, den zweiten Import mit Alias `as app_settings` weglassen und direkt `settings` weiterverwenden; prüfe den bestehenden Import vor dem Einfügen.)

Füge ein kleines Schema für den Lösch-Request hinzu (direkt in `auth.py`, da nur hier gebraucht):
```python
class DeleteAccountRequest(BaseModel):
    password: str | None = None
```

Füge die Endpunkte am Ende der Datei hinzu:
```python
@router.delete("/me", status_code=204)
def delete_account(
    payload: DeleteAccountRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.password_hash is not None:
        if not payload.password or not verify_password(payload.password, current_user.password_hash):
            raise HTTPException(401, "Passwort falsch")

    from app.services.storage_paths import incoming_dir_for_client, processed_dir_for_client_date  # noqa: F401
    for client_row in current_user.clients:
        for base_dir in (settings.photos_incoming_dir, settings.photos_processed_dir, settings.photos_normalized_dir):
            client_dir = base_dir / str(client_row.id)
            if client_dir.exists():
                shutil.rmtree(client_dir, ignore_errors=True)

    db.delete(current_user)  # cascaded: Client -> Pose/DayLog/Photo/AppSetting, EmailToken
    db.commit()
    response.delete_cookie(SESSION_COOKIE_NAME, secure=True)


@router.get("/me/export")
def export_my_data(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.models.day_log import DayLog
    from app.models.photo import Photo

    clients_data = []
    for c in current_user.clients:
        day_logs = db.query(DayLog).filter(DayLog.client_id == c.id).all()
        photos = db.query(Photo).filter(Photo.client_id == c.id).all()
        clients_data.append({
            "id": c.id,
            "name": c.name,
            "height_cm": c.height_cm,
            "birth_date": c.birth_date.isoformat() if c.birth_date else None,
            "gender": c.gender,
            "start_date": c.start_date.isoformat() if c.start_date else None,
            "day_logs": [
                {"date": dl.date.isoformat(), "weight_kg": dl.weight_kg, "notes": dl.notes}
                for dl in day_logs
            ],
            "photos": [
                {"filename": p.filename, "taken_at": p.taken_at.isoformat(), "original_path": p.original_path}
                for p in photos
            ],
        })

    return {
        "email": current_user.email,
        "display_name": current_user.display_name,
        "account_type": current_user.account_type.value,
        "created_at": current_user.created_at.isoformat(),
        "clients": clients_data,
    }
```

- [ ] **Step 4: Test laufen lassen, Erfolg bestätigen**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_account_deletion_export.py -v`
Expected: `4 passed`

- [ ] **Step 5: Volle Suite laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest -v`
Expected: alle grün.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/auth.py backend/tests/test_account_deletion_export.py
git commit -m "feat: add account deletion (with file cleanup) and data export endpoints"
```

---

## Part 7 — Frontend

### Task 12: Signup-Seite + E-Mail-Verifizierungs-Seite

**Files:**
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/pages/Signup.tsx`
- Create: `frontend/src/pages/VerifyEmail.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: `api/client.ts` um Signup/Verify erweitern**

Erweitere den `auth`-Block in `frontend/src/api/client.ts`:
```typescript
  auth: {
    login: (email: string, password: string) =>
      client.post<CurrentUser>("/auth/login", { email, password }).then((r) => r.data),
    logout: () => client.post("/auth/logout"),
    me: () => client.get<CurrentUser>("/auth/me").then((r) => r.data),
    switchToCoach: () =>
      client.post<CurrentUser>("/auth/switch-to-coach").then((r) => r.data),
    signup: (payload: { email: string; password: string; display_name: string; privacy_accepted: boolean }) =>
      client.post<CurrentUser>("/auth/signup", payload).then((r) => r.data),
    verifyEmail: (token: string) =>
      client.get("/auth/verify-email", { params: { token } }).then((r) => r.data),
    resendVerification: (email: string) => client.post("/auth/resend-verification", { email }),
    forgotPassword: (email: string) => client.post("/auth/forgot-password", { email }),
    resetPassword: (token: string, new_password: string) =>
      client.post("/auth/reset-password", { token, new_password }),
    deleteAccount: (password?: string) =>
      client.delete("/auth/me", { data: { password } }),
    exportData: () => client.get("/auth/me/export").then((r) => r.data),
  },
```

- [ ] **Step 2: `Signup.tsx` schreiben**

```tsx
// frontend/src/pages/Signup.tsx
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";

export default function Signup() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [privacyAccepted, setPrivacyAccepted] = useState(false);
  const navigate = useNavigate();

  const signupMutation = useMutation({
    mutationFn: () =>
      api.auth.signup({ email, password, display_name: displayName, privacy_accepted: privacyAccepted }),
    onSuccess: () => navigate("/signup-success"),
  });

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          signupMutation.mutate();
        }}
        className="w-full max-w-sm space-y-4 rounded-xl border border-white/5 bg-surface p-6"
      >
        <h1 className="text-xl font-semibold text-white">
          BodyComp <span className="text-accent">Tracker</span>
        </h1>
        <label className="flex flex-col gap-1 text-sm text-slate-400">
          Name
          <input
            required
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-slate-400">
          E-Mail
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-slate-400">
          Passwort (mind. 8 Zeichen)
          <input
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
          />
        </label>
        <label className="flex items-start gap-2 text-sm text-slate-400">
          <input
            type="checkbox"
            required
            checked={privacyAccepted}
            onChange={(e) => setPrivacyAccepted(e.target.checked)}
            className="mt-1"
          />
          <span>
            Ich akzeptiere die{" "}
            <Link to="/datenschutz" className="text-accent hover:underline" target="_blank">
              Datenschutzerklärung
            </Link>
          </span>
        </label>
        {signupMutation.isError && (
          <p className="text-sm text-red-400">
            Registrierung fehlgeschlagen - E-Mail evtl. bereits vergeben.
          </p>
        )}
        <button
          type="submit"
          disabled={signupMutation.isPending}
          className="w-full rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-50"
        >
          {signupMutation.isPending ? "Registrieren…" : "Registrieren"}
        </button>
        <p className="text-center text-sm text-slate-400">
          Schon registriert?{" "}
          <Link to="/login" className="text-accent hover:underline">
            Einloggen
          </Link>
        </p>
      </form>
    </div>
  );
}
```

- [ ] **Step 3: `SignupSuccess.tsx` (Hinweisseite) und `VerifyEmail.tsx` schreiben**

```tsx
// frontend/src/pages/SignupSuccess.tsx
import { Link } from "react-router-dom";

export default function SignupSuccess() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-4 rounded-xl border border-white/5 bg-surface p-6 text-center">
        <h1 className="text-xl font-semibold text-white">Fast geschafft!</h1>
        <p className="text-sm text-slate-400">
          Wir haben dir eine E-Mail geschickt. Bitte klicke auf den Bestätigungslink, um dein
          Konto zu aktivieren.
        </p>
        <Link to="/login" className="text-accent hover:underline text-sm">
          Zurück zum Login
        </Link>
      </div>
    </div>
  );
}
```

```tsx
// frontend/src/pages/VerifyEmail.tsx
import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { api } from "../api/client";

export default function VerifyEmail() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");
  const [status, setStatus] = useState<"pending" | "success" | "error">("pending");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      return;
    }
    api.auth
      .verifyEmail(token)
      .then(() => setStatus("success"))
      .catch(() => setStatus("error"));
  }, [token]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-4 rounded-xl border border-white/5 bg-surface p-6 text-center">
        {status === "pending" && <p className="text-slate-400">Bestätige…</p>}
        {status === "success" && (
          <>
            <h1 className="text-xl font-semibold text-white">E-Mail bestätigt!</h1>
            <Link to="/login" className="text-accent hover:underline text-sm">
              Jetzt einloggen
            </Link>
          </>
        )}
        {status === "error" && (
          <>
            <h1 className="text-xl font-semibold text-white">Link ungültig</h1>
            <p className="text-sm text-slate-400">
              Der Link ist abgelaufen oder wurde bereits verwendet.
            </p>
            <Link to="/login" className="text-accent hover:underline text-sm">
              Zurück zum Login
            </Link>
          </>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Routen in `App.tsx` ergänzen**

Füge zu `frontend/src/App.tsx` die neuen Imports und Routen hinzu:
```tsx
import Signup from "./pages/Signup";
import SignupSuccess from "./pages/SignupSuccess";
import VerifyEmail from "./pages/VerifyEmail";
```
Und innerhalb von `<Routes>`, vor dem `<Route element={<RequireAuth />}>`-Block:
```tsx
      <Route path="/signup" element={<Signup />} />
      <Route path="/signup-success" element={<SignupSuccess />} />
      <Route path="/verify-email" element={<VerifyEmail />} />
```

- [ ] **Step 5: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/pages/Signup.tsx frontend/src/pages/SignupSuccess.tsx frontend/src/pages/VerifyEmail.tsx frontend/src/App.tsx
git commit -m "feat: add signup page, verification success/error page, routes"
```

---

### Task 13: Passwort-Reset-Seiten + Login-Seite erweitern

**Files:**
- Create: `frontend/src/pages/ForgotPassword.tsx`
- Create: `frontend/src/pages/ResetPassword.tsx`
- Modify: `frontend/src/pages/Login.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: `ForgotPassword.tsx` schreiben**

```tsx
// frontend/src/pages/ForgotPassword.tsx
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const mutation = useMutation({ mutationFn: () => api.auth.forgotPassword(email) });

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-4 rounded-xl border border-white/5 bg-surface p-6">
        <h1 className="text-xl font-semibold text-white">Passwort vergessen</h1>
        {mutation.isSuccess ? (
          <p className="text-sm text-slate-400">
            Falls ein Account mit dieser E-Mail existiert, wurde eine Mail mit einem Reset-Link
            verschickt.
          </p>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              mutation.mutate();
            }}
            className="space-y-4"
          >
            <label className="flex flex-col gap-1 text-sm text-slate-400">
              E-Mail
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
              />
            </label>
            <button
              type="submit"
              disabled={mutation.isPending}
              className="w-full rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-50"
            >
              {mutation.isPending ? "Senden…" : "Link anfordern"}
            </button>
          </form>
        )}
        <Link to="/login" className="block text-center text-sm text-accent hover:underline">
          Zurück zum Login
        </Link>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: `ResetPassword.tsx` schreiben**

```tsx
// frontend/src/pages/ResetPassword.tsx
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";

export default function ResetPassword() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [password, setPassword] = useState("");
  const navigate = useNavigate();

  const mutation = useMutation({
    mutationFn: () => api.auth.resetPassword(token, password),
    onSuccess: () => navigate("/login"),
  });

  if (!token) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4">
        <p className="text-slate-400">Ungültiger Link.</p>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate();
        }}
        className="w-full max-w-sm space-y-4 rounded-xl border border-white/5 bg-surface p-6"
      >
        <h1 className="text-xl font-semibold text-white">Neues Passwort setzen</h1>
        <label className="flex flex-col gap-1 text-sm text-slate-400">
          Neues Passwort (mind. 8 Zeichen)
          <input
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
          />
        </label>
        {mutation.isError && (
          <p className="text-sm text-red-400">Link ungültig oder abgelaufen.</p>
        )}
        <button
          type="submit"
          disabled={mutation.isPending}
          className="w-full rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-50"
        >
          {mutation.isPending ? "Speichern…" : "Passwort setzen"}
        </button>
        <Link to="/login" className="block text-center text-sm text-accent hover:underline">
          Zurück zum Login
        </Link>
      </form>
    </div>
  );
}
```

- [ ] **Step 3: `Login.tsx` erweitern** — Google-Button, Signup-Link, Verifizierungs-Fehler mit Resend-Button

Ersetze den kompletten Inhalt von `frontend/src/pages/Login.tsx`:
```tsx
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const loginMutation = useMutation({
    mutationFn: () => api.auth.login(email, password),
    onSuccess: (user) => {
      queryClient.setQueryData(["auth", "me"], user);
      navigate(user.account_type === "coach" ? "/" : "/redirect-to-my-client");
    },
  });

  const resendMutation = useMutation({
    mutationFn: () => api.auth.resendVerification(email),
  });

  const isUnverifiedError =
    loginMutation.isError &&
    (loginMutation.error as any)?.response?.status === 403;

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          loginMutation.mutate();
        }}
        className="w-full max-w-sm space-y-4 rounded-xl border border-white/5 bg-surface p-6"
      >
        <h1 className="text-xl font-semibold text-white">
          BodyComp <span className="text-accent">Tracker</span>
        </h1>
        <label className="flex flex-col gap-1 text-sm text-slate-400">
          E-Mail
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-slate-400">
          Passwort
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
          />
        </label>
        {isUnverifiedError ? (
          <div className="text-sm text-red-400">
            <p>Bitte bestätige zuerst deine E-Mail-Adresse.</p>
            <button
              type="button"
              onClick={() => resendMutation.mutate()}
              disabled={resendMutation.isPending}
              className="mt-1 text-accent hover:underline disabled:opacity-50"
            >
              {resendMutation.isSuccess ? "Mail erneut gesendet" : "Bestätigungsmail erneut senden"}
            </button>
          </div>
        ) : (
          loginMutation.isError && (
            <p className="text-sm text-red-400">E-Mail oder Passwort falsch.</p>
          )
        )}
        <button
          type="submit"
          disabled={loginMutation.isPending}
          className="w-full rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-50"
        >
          {loginMutation.isPending ? "Einloggen…" : "Einloggen"}
        </button>
        <a
          href="/api/auth/google/login"
          className="flex w-full items-center justify-center gap-2 rounded-lg border border-white/10 bg-black/30 px-4 py-2 text-sm font-medium text-white hover:bg-black/50"
        >
          Mit Google anmelden
        </a>
        <div className="flex justify-between text-sm">
          <Link to="/signup" className="text-accent hover:underline">
            Registrieren
          </Link>
          <Link to="/forgot-password" className="text-accent hover:underline">
            Passwort vergessen?
          </Link>
        </div>
      </form>
    </div>
  );
}
```

- [ ] **Step 4: Routen in `App.tsx` ergänzen**

Füge zu `frontend/src/App.tsx` hinzu:
```tsx
import ForgotPassword from "./pages/ForgotPassword";
import ResetPassword from "./pages/ResetPassword";
```
Und im `<Routes>`-Block (öffentlicher Bereich, vor `RequireAuth`):
```tsx
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
```

- [ ] **Step 5: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/ForgotPassword.tsx frontend/src/pages/ResetPassword.tsx frontend/src/pages/Login.tsx frontend/src/App.tsx
git commit -m "feat: add forgot/reset password pages, Google login button, signup link on Login"
```

---

### Task 14: Account-Löschung + Datenexport im Frontend

**Files:**
- Modify: `frontend/src/pages/Account.tsx`

- [ ] **Step 1: Buttons in `Account.tsx` ergänzen**

Lies `frontend/src/pages/Account.tsx` vollständig, um die bestehende Struktur (Kontotyp-Umschalter, `DisplaySettingsSection`, Gemini-Key-Bereich) zu sehen. Füge am Ende des gerenderten JSX (innerhalb des äußeren `<div className="max-w-xl space-y-6">`, nach den bestehenden Abschnitten) einen neuen Abschnitt hinzu:

```tsx
function DangerZoneSection() {
  const [showConfirm, setShowConfirm] = useState(false);
  const [password, setPassword] = useState("");
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const deleteMutation = useMutation({
    mutationFn: () => api.auth.deleteAccount(password || undefined),
    onSuccess: () => {
      queryClient.clear();
      navigate("/login");
    },
  });

  const exportMutation = useMutation({
    mutationFn: api.auth.exportData,
    onSuccess: (data) => {
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "bodycomp-daten-export.json";
      a.click();
      URL.revokeObjectURL(url);
    },
  });

  return (
    <div className="rounded-xl border border-red-900/40 bg-surface p-4">
      <h2 className="mb-1 text-lg font-semibold text-white">Konto-Verwaltung</h2>
      <div className="mt-3 flex flex-col gap-3">
        <button
          onClick={() => exportMutation.mutate()}
          disabled={exportMutation.isPending}
          className="w-fit rounded-lg border border-white/10 px-4 py-2 text-sm text-slate-300 hover:bg-black/30"
        >
          {exportMutation.isPending ? "Exportiere…" : "Meine Daten exportieren"}
        </button>

        {!showConfirm ? (
          <button
            onClick={() => setShowConfirm(true)}
            className="w-fit rounded-lg border border-red-900/50 px-4 py-2 text-sm text-red-400 hover:bg-red-950/30"
          >
            Konto löschen
          </button>
        ) : (
          <div className="space-y-2 rounded-lg border border-red-900/50 p-3">
            <p className="text-sm text-red-400">
              Das löscht dein Konto und ALLE zugehörigen Daten (Kunden, Fotos, Verlauf)
              unwiderruflich.
            </p>
            <input
              type="password"
              placeholder="Passwort zur Bestätigung"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white focus:border-accent focus:outline-none"
            />
            <div className="flex gap-2">
              <button
                onClick={() => deleteMutation.mutate()}
                disabled={deleteMutation.isPending}
                className="rounded-lg bg-red-700 px-4 py-2 text-sm font-medium text-white hover:bg-red-600 disabled:opacity-50"
              >
                {deleteMutation.isPending ? "Lösche…" : "Endgültig löschen"}
              </button>
              <button
                onClick={() => setShowConfirm(false)}
                className="rounded-lg border border-white/10 px-4 py-2 text-sm text-slate-300"
              >
                Abbrechen
              </button>
            </div>
            {deleteMutation.isError && (
              <p className="text-sm text-red-400">Löschen fehlgeschlagen - Passwort korrekt?</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
```

Füge `<DangerZoneSection />` im JSX der Haupt-`Account`-Komponente hinzu, als letztes Element vor dem schließenden `</div>` des äußeren Containers. Ergänze die Imports oben in der Datei um `useNavigate` (`import { useNavigate } from "react-router-dom";`) - `useState`, `useMutation`, `useQueryClient` sind bereits importiert.

Bei Google-only-Accounts (kein Passwort) soll das Passwortfeld nicht zwingend nötig sein - das Formular erlaubt bereits ein leeres Feld (`password || undefined` im `deleteMutation`), das Backend prüft selbst, ob überhaupt ein Passwort gesetzt ist.

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Account.tsx
git commit -m "feat: add account deletion and data export to Account page"
```

---

### Task 15: Rechts-Platzhalterseiten

**Files:**
- Create: `frontend/src/pages/legal/Datenschutz.tsx`
- Create: `frontend/src/pages/legal/Impressum.tsx`
- Create: `frontend/src/pages/legal/Agb.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Gemeinsame Platzhalter-Komponente + drei Seiten**

```tsx
// frontend/src/pages/legal/LegalPagePlaceholder.tsx
import { Link } from "react-router-dom";

export default function LegalPagePlaceholder({ title }: { title: string }) {
  return (
    <div className="mx-auto max-w-2xl px-4 py-10 text-slate-300">
      <div className="mb-4 rounded-lg border border-yellow-600/40 bg-yellow-950/20 p-3 text-sm text-yellow-400">
        ENTWURF — dieser Text muss vor echtem Live-Betrieb rechtlich geprüft werden.
      </div>
      <h1 className="mb-4 text-2xl font-semibold text-white">{title}</h1>
      <p className="text-slate-400">
        Platzhaltertext. Wird vor öffentlichem Launch durch rechtsverbindlichen Inhalt ersetzt.
      </p>
      <Link to="/login" className="mt-6 inline-block text-accent hover:underline">
        Zurück
      </Link>
    </div>
  );
}
```

```tsx
// frontend/src/pages/legal/Datenschutz.tsx
import LegalPagePlaceholder from "./LegalPagePlaceholder";

export default function Datenschutz() {
  return <LegalPagePlaceholder title="Datenschutzerklärung" />;
}
```

```tsx
// frontend/src/pages/legal/Impressum.tsx
import LegalPagePlaceholder from "./LegalPagePlaceholder";

export default function Impressum() {
  return <LegalPagePlaceholder title="Impressum" />;
}
```

```tsx
// frontend/src/pages/legal/Agb.tsx
import LegalPagePlaceholder from "./LegalPagePlaceholder";

export default function Agb() {
  return <LegalPagePlaceholder title="Allgemeine Geschäftsbedingungen" />;
}
```

- [ ] **Step 2: Routen in `App.tsx` ergänzen**

Füge zu `frontend/src/App.tsx` hinzu:
```tsx
import Datenschutz from "./pages/legal/Datenschutz";
import Impressum from "./pages/legal/Impressum";
import Agb from "./pages/legal/Agb";
```
Und im öffentlichen Routen-Bereich:
```tsx
      <Route path="/datenschutz" element={<Datenschutz />} />
      <Route path="/impressum" element={<Impressum />} />
      <Route path="/agb" element={<Agb />} />
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/legal frontend/src/App.tsx
git commit -m "feat: add placeholder legal pages (Datenschutz, Impressum, AGB)"
```

---

## Abschließende manuelle Verifikation

Nach Abschluss aller 15 Tasks:

- [ ] Volle Backend-Suite: `cd backend && .venv/Scripts/python -m pytest -v` — alle grün.
- [ ] Frontend-Typecheck: `cd frontend && npx tsc --noEmit` — keine Fehler.
- [ ] Google Cloud Projekt + OAuth-Client anlegen (Client-ID/Secret in `.env` eintragen, Redirect-URI `http://localhost:8000/api/auth/google/callback` in der Google Cloud Console hinterlegen).
- [ ] Resend-Account anlegen, API-Key in `.env` eintragen (Sandbox-Modus, Test-Empfänger-Adresse bei Resend verifizieren).
- [ ] Manueller Durchlauf: Signup mit E-Mail+Passwort → Bestätigungsmail kommt an (an die Resend-Sandbox-Testadresse) → Link klicken → Login funktioniert.
- [ ] Manueller Durchlauf: "Mit Google anmelden" → Consent-Screen → landet eingeloggt im Dashboard.
- [ ] Manueller Durchlauf: Passwort vergessen → Mail kommt an → neues Passwort setzen → alter Login (falls noch offen in einem anderen Tab) wird abgelehnt.
- [ ] Manueller Durchlauf: Account löschen → alle Daten weg, Redirect zu `/login`.
- [ ] Manueller Durchlauf: Datenexport → JSON-Datei mit korrekten Daten wird heruntergeladen.
