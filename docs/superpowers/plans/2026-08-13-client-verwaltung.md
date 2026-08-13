# Client-/Mandantenverwaltung Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn BodyComp Tracker from a single-user app into a multi-tenant app: accounts log in (cookie session), each account has one or more `Client` profiles (athletes), all existing data (Pose/DayLog/Photo) becomes client-scoped, and the existing UI moves under `/clients/:id/*`. Accounts are `single` (no dashboard, straight into their one auto-created client) or `coach` (dashboard with a client list).

**Architecture:** FastAPI backend gets a `User` + `Client` model, httpOnly signed-cookie sessions, and every existing router nested under `/api/clients/{client_id}/...` behind an ownership-checking dependency. React frontend gets a login page, a dashboard, and the existing pages move under `/clients/:id/*`. A one-time startup migration moves the current single-tenant data into a `Client` named "Mein Profil" owned by a new `coach` account.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, SQLite, `bcrypt` (password hashing), `itsdangerous` (signed session cookies), pytest + `httpx` TestClient (new — no test infra exists yet), React 18, React Router, TanStack Query, axios.

**Spec:** `docs/superpowers/specs/2026-08-13-client-verwaltung-design.md`

---

## Part 1 — Backend

### Task 1: Test infrastructure

The codebase has zero test infrastructure today (`backend/tests/__init__.py` is empty, `pytest` isn't even in `requirements.txt`). This task adds a minimal pytest + FastAPI `TestClient` setup with an isolated temp-file SQLite DB per test, which every later backend task's tests build on.

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_health.py`

- [ ] **Step 1: Add test dependencies**

Add these lines to `backend/requirements.txt`:

```
pytest>=8.3.3
httpx>=0.27.2
bcrypt>=4.2.0
itsdangerous>=2.2.0
```

- [ ] **Step 2: Install dependencies**

Run: `cd backend && .venv/Scripts/python -m pip install -r requirements.txt`
Expected: all four new packages install without error.

- [ ] **Step 3: Write `conftest.py`**

```python
"""
Pytest-Fixtures: jede Testfunktion bekommt eine frische, leere SQLite-DB in
einer temporären Datei (nicht in-memory, weil die App mit
`connect_args={"check_same_thread": False}` arbeitet und manche Endpunkte
mehrere Connections aus demselben Engine ziehen - eine echte Datei verhält
sich da vorhersehbarer als eine In-Memory-DB, die pro Connection neu wäre).
"""
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app


@pytest.fixture()
def db_session():
    tmp_dir = tempfile.mkdtemp()
    db_path = Path(tmp_dir) / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
```

- [ ] **Step 4: Write a smoke test**

```python
def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 5: Run it**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_health.py -v`
Expected: `1 passed`. If it fails on app startup (e.g. `lifespan` touching the real `data/` dir), that's fine for this POC — the real `engine`/`data_dir` still get created once at import time; this smoke test only proves the TestClient + DB-override wiring works, which later tasks depend on.

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/tests/conftest.py backend/tests/test_health.py
git commit -m "test: add pytest + TestClient infrastructure with isolated per-test SQLite DB"
```

---

### Task 2: `User` model + password hashing

**Files:**
- Create: `backend/app/models/user.py`
- Create: `backend/app/services/auth.py`
- Test: `backend/tests/test_auth_service.py`
- Modify: `backend/app/main.py` (register model for `create_all`)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_auth_service.py
from app.services.auth import hash_password, verify_password


def test_hash_password_is_not_plaintext():
    hashed = hash_password("Grindcore123!")
    assert hashed != "Grindcore123!"
    assert hashed.startswith("$2b$")


def test_verify_password_correct():
    hashed = hash_password("Grindcore123!")
    assert verify_password("Grindcore123!", hashed) is True


def test_verify_password_wrong():
    hashed = hash_password("Grindcore123!")
    assert verify_password("wrong-password", hashed) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_auth_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.auth'`

- [ ] **Step 3: Write `app/services/auth.py`**

```python
"""
Passwort-Hashing für die Account-Authentifizierung. bcrypt statt eines
selbstgebauten Hashings, weil bcrypt Salting und einen konfigurierbaren
Work-Factor eingebaut hat - der Industriestandard für Passwort-Hashes.
"""
import bcrypt


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_auth_service.py -v`
Expected: `3 passed`

- [ ] **Step 5: Write `app/models/user.py`**

```python
"""
User = ein Account, der sich einloggt. Kann `single` (nur eigener
Fortschritt, kein Dashboard) oder `coach` (mehrere Kunden, Dashboard)
sein - siehe Design-Spec Abschnitt "Kontotyp". Jeder User bekommt bei
Anlage automatisch genau einen Client (siehe app/models/client.py),
unabhängig vom account_type.
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
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_type: Mapped[AccountType] = mapped_column(
        Enum(AccountType), default=AccountType.SINGLE, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    clients: Mapped[list["Client"]] = relationship(  # noqa: F821
        back_populates="owner", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} account_type={self.account_type}>"
```

- [ ] **Step 6: Register the model in `main.py`**

In `backend/app/main.py`, add to the imports (this file already has a `# noqa: F401` import pattern for `app_setting` — follow it):

```python
from app.models import app_setting  # noqa: F401 - Import registriert Table bei create_all
from app.models import user  # noqa: F401 - Import registriert Table bei create_all
```

- [ ] **Step 7: Verify the table gets created**

```python
# backend/tests/test_auth_service.py — append this test
def test_user_table_exists(db_session):
    from app.models.user import User

    db_session.add(
        User(
            email="test@example.com",
            password_hash="hashed",
            display_name="Test",
        )
    )
    db_session.commit()
    result = db_session.query(User).filter(User.email == "test@example.com").first()
    assert result is not None
    assert result.account_type.value == "single"
```

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_auth_service.py -v`
Expected: `4 passed`

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/user.py backend/app/services/auth.py backend/app/main.py backend/tests/test_auth_service.py
git commit -m "feat: add User model with bcrypt password hashing"
```

---

### Task 3: `Client` model

**Files:**
- Create: `backend/app/models/client.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_client_model.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_client_model.py
from app.models.client import Client
from app.models.user import User


def test_client_belongs_to_user(db_session):
    user = User(email="a@b.com", password_hash="x", display_name="A")
    db_session.add(user)
    db_session.flush()

    client_row = Client(owner_id=user.id, name="Mein Profil")
    db_session.add(client_row)
    db_session.commit()

    assert client_row.id is not None
    assert user.clients[0].name == "Mein Profil"


def test_client_deleted_when_owner_deleted(db_session):
    user = User(email="a@b.com", password_hash="x", display_name="A")
    db_session.add(user)
    db_session.flush()
    db_session.add(Client(owner_id=user.id, name="Mein Profil"))
    db_session.commit()

    db_session.delete(user)
    db_session.commit()

    assert db_session.query(Client).count() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_client_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.client'`

- [ ] **Step 3: Write `app/models/client.py`**

```python
"""
Client = das Athleten-Profil (bisher: "die App", jetzt eine von mehreren
verwaltbaren Personen unter einem Account). Jede Pose/jeder DayLog/jedes
Photo hängt an genau einem Client. Jeder User (single oder coach) hat
mindestens einen Client - siehe Design-Spec Abschnitt "Kontotyp".
"""
from datetime import date as date_, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String
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
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(50), nullable=True)
    start_date: Mapped[date_ | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    owner: Mapped["User"] = relationship(back_populates="clients")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Client id={self.id} name={self.name!r} owner_id={self.owner_id}>"
```

- [ ] **Step 4: Register the model in `main.py`**

Add below the `user` import:

```python
from app.models import client  # noqa: F401 - Import registriert Table bei create_all
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_client_model.py -v`
Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/client.py backend/app/main.py backend/tests/test_client_model.py
git commit -m "feat: add Client model owned by User, cascade-deleted with owner"
```

---

### Task 4: Session cookie auth (login/logout, `get_current_user`)

**Files:**
- Create: `backend/app/schemas/auth.py`
- Modify: `backend/app/services/auth.py`
- Create: `backend/app/routers/auth.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_auth_router.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_auth_router.py
from app.models.user import User
from app.services.auth import hash_password


def _make_user(db_session, email="basti@example.com", password="Grindcore123!"):
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name="Basti",
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_login_with_correct_credentials_sets_cookie(client, db_session):
    _make_user(db_session)
    response = client.post(
        "/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"}
    )
    assert response.status_code == 200
    assert "session" in response.cookies


def test_login_with_wrong_password_fails(client, db_session):
    _make_user(db_session)
    response = client.post(
        "/api/auth/login", json={"email": "basti@example.com", "password": "wrong"}
    )
    assert response.status_code == 401
    assert "session" not in response.cookies


def test_login_with_unknown_email_fails(client, db_session):
    response = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": "x"}
    )
    assert response.status_code == 401


def test_me_requires_session(client, db_session):
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_me_returns_current_user_after_login(client, db_session):
    _make_user(db_session)
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "basti@example.com"
    assert body["display_name"] == "Basti"
    assert body["account_type"] == "single"


def test_logout_clears_session(client, db_session):
    _make_user(db_session)
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})
    client.post("/api/auth/logout")
    response = client.get("/api/auth/me")
    assert response.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_auth_router.py -v`
Expected: FAIL with 404s (no `/api/auth/*` routes exist yet)

- [ ] **Step 3: Write `app/schemas/auth.py`**

```python
from app.models.user import AccountType
from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    account_type: AccountType

    class Config:
        from_attributes = True
```

- [ ] **Step 4: Add signed-cookie helpers to `app/services/auth.py`**

Append to the existing file:

```python
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.core.config import settings

SESSION_COOKIE_NAME = "session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30  # 30 Tage

_serializer = URLSafeTimedSerializer(settings.session_secret_key, salt="session-cookie")


def create_session_token(user_id: int) -> str:
    return _serializer.dumps({"user_id": user_id})


def verify_session_token(token: str) -> int | None:
    """Gibt die user_id zurück, wenn die Signatur gültig und das Cookie
    nicht abgelaufen ist - sonst None (nie eine Exception nach außen)."""
    try:
        data = _serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
    except BadSignature:
        return None
    return data.get("user_id")
```

- [ ] **Step 5: Add `session_secret_key` to config**

In `backend/app/core/config.py`, add this field to the `Settings` class (right after `allowed_extensions`):

```python
    # Signiert die Session-Cookies (siehe services/auth.py). In Produktion
    # per BODYCOMP_SESSION_SECRET_KEY überschreiben - der Default ist nur
    # fürs lokale Dev-Setup gedacht.
    session_secret_key: str = "dev-only-insecure-secret-change-me"
```

- [ ] **Step 6: Write `app/routers/auth.py`**

```python
"""Login/Logout via signiertes, httpOnly Session-Cookie - siehe
Design-Spec Abschnitt "Authentifizierung"."""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, UserOut
from app.services.auth import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    create_session_token,
    verify_password,
    verify_session_token,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def get_current_user(
    session: str | None = None,
    db: Session = Depends(get_db),
) -> User:
    """FastAPI-Dependency: liest das Session-Cookie, validiert Signatur +
    Ablauf, lädt den User. Wirft 401, wenn irgendwas davon fehlschlägt."""
    raise NotImplementedError  # wird in Schritt 7 durch die echte Version ersetzt


@router.post("/login", response_model=UserOut)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "E-Mail oder Passwort falsch")

    token = create_session_token(user.id)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
    )
    return user


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user
```

- [ ] **Step 7: Replace the placeholder `get_current_user` with a real cookie-reading version**

FastAPI resolves cookie values via `fastapi.Cookie`, not a plain function argument default — replace the whole function in `app/routers/auth.py`:

```python
from fastapi import Cookie

def get_current_user(
    session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI-Dependency: liest das Session-Cookie, validiert Signatur +
    Ablauf, lädt den User. Wirft 401, wenn irgendwas davon fehlschlägt."""
    if session is None:
        raise HTTPException(401, "Nicht eingeloggt")
    user_id = verify_session_token(session)
    if user_id is None:
        raise HTTPException(401, "Session ungültig oder abgelaufen")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(401, "Session ungültig oder abgelaufen")
    return user
```

Also add the `Cookie` import to the top-level `from fastapi import ...` line instead of a separate one:

```python
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
```

(remove the now-duplicate `from fastapi import Cookie` you added inline above)

- [ ] **Step 8: Register the router in `main.py`**

```python
from app.routers import auth, comparisons, day_logs, photos, poses, settings as settings_router
...
app.include_router(auth.router)
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_auth_router.py -v`
Expected: `6 passed`

- [ ] **Step 10: Commit**

```bash
git add backend/app/schemas/auth.py backend/app/services/auth.py backend/app/routers/auth.py backend/app/core/config.py backend/app/main.py backend/tests/test_auth_router.py
git commit -m "feat: add login/logout with signed httpOnly session cookies"
```

---

### Task 5: `Client` CRUD router + ownership dependency

**Files:**
- Create: `backend/app/schemas/client.py`
- Create: `backend/app/routers/clients.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_clients_router.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_clients_router.py
from app.models.user import User
from app.services.auth import hash_password


def _login(client, db_session, email="a@b.com", password="pw12345"):
    user = User(email=email, password_hash=hash_password(password), display_name="A")
    db_session.add(user)
    db_session.commit()
    client.post("/api/auth/login", json={"email": email, "password": password})
    return user


def test_create_and_list_clients(client, db_session):
    _login(client, db_session)

    create_resp = client.post(
        "/api/clients",
        json={"name": "Max Mustermann", "height_cm": 180, "age": 28, "gender": "männlich", "start_date": "2026-01-01"},
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["name"] == "Max Mustermann"
    assert created["height_cm"] == 180

    list_resp = client.get("/api/clients")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


def test_cannot_see_other_users_clients(client, db_session):
    owner_a = _login(client, db_session, email="a@b.com", password="pw12345")
    resp = client.post("/api/clients", json={"name": "A's Kunde"})
    client_id = resp.json()["id"]
    client.post("/api/auth/logout")

    _login(client, db_session, email="c@d.com", password="pw67890")
    get_resp = client.get(f"/api/clients/{client_id}")
    assert get_resp.status_code == 404

    list_resp = client.get("/api/clients")
    assert list_resp.json() == []


def test_update_client_metrics(client, db_session):
    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()

    patch_resp = client.patch(f"/api/clients/{created['id']}", json={"height_cm": 185.5})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["height_cm"] == 185.5
    assert patch_resp.json()["name"] == "Max"


def test_unauthenticated_request_rejected(client, db_session):
    response = client.get("/api/clients")
    assert response.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_clients_router.py -v`
Expected: FAIL with 404s (no `/api/clients` routes yet)

- [ ] **Step 3: Write `app/schemas/client.py`**

```python
from datetime import date as date_, datetime

from pydantic import BaseModel, Field


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    height_cm: float | None = None
    age: int | None = None
    gender: str | None = None
    start_date: date_ | None = None


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    height_cm: float | None = None
    age: int | None = None
    gender: str | None = None
    start_date: date_ | None = None


class ClientOut(BaseModel):
    id: int
    name: str
    height_cm: float | None
    age: int | None
    gender: str | None
    start_date: date_ | None
    created_at: datetime

    class Config:
        from_attributes = True
```

- [ ] **Step 4: Write `app/routers/clients.py`**

```python
"""
Kunden-Verwaltung: Liste/Anlegen/Bearbeiten der Client-Profile eines
Accounts, plus die zentrale `get_owned_client`-Dependency, die JEDER
client-scoped Router (photos/poses/day_logs/comparisons) importiert, um
sicherzustellen, dass ein Account nie auf fremde Kunden zugreifen kann.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.client import Client
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.client import ClientCreate, ClientOut, ClientUpdate

router = APIRouter(prefix="/api/clients", tags=["clients"])


def get_owned_client(
    client_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Client:
    """Lädt den Client NUR, wenn er dem eingeloggten Account gehört -
    sonst 404 (nicht 403), damit die API nicht mal verrät, ob eine
    fremde Kunden-ID überhaupt existiert. Wird von jedem client-scoped
    Endpunkt als Dependency genutzt."""
    client_row = (
        db.query(Client)
        .filter(Client.id == client_id, Client.owner_id == current_user.id)
        .first()
    )
    if client_row is None:
        raise HTTPException(404, "Kunde nicht gefunden")
    return client_row


@router.get("", response_model=list[ClientOut])
def list_clients(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return (
        db.query(Client)
        .filter(Client.owner_id == current_user.id)
        .order_by(Client.created_at)
        .all()
    )


@router.post("", response_model=ClientOut, status_code=201)
def create_client(
    payload: ClientCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    client_row = Client(owner_id=current_user.id, **payload.model_dump())
    db.add(client_row)
    db.commit()
    db.refresh(client_row)
    return client_row


@router.get("/{client_id}", response_model=ClientOut)
def get_client(client_row: Client = Depends(get_owned_client)):
    return client_row


@router.patch("/{client_id}", response_model=ClientOut)
def update_client(
    payload: ClientUpdate,
    client_row: Client = Depends(get_owned_client),
    db: Session = Depends(get_db),
):
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(client_row, field, value)
    db.commit()
    db.refresh(client_row)
    return client_row
```

- [ ] **Step 5: Register the router in `main.py`**

```python
from app.routers import auth, clients, comparisons, day_logs, photos, poses, settings as settings_router
...
app.include_router(clients.router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_clients_router.py -v`
Expected: `4 passed`

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/client.py backend/app/routers/clients.py backend/app/main.py backend/tests/test_clients_router.py
git commit -m "feat: add Client CRUD router with ownership-checking dependency"
```

---

### Task 6: Auto-create one `Client` when a `User` is created

Per the Kontotyp design: every account gets exactly one `Client` at creation time, named after `display_name`. This is what makes `single` → `coach` switching a pure flag-flip later (Task 9) with no data migration.

**Files:**
- Modify: `backend/app/routers/auth.py` — not this file, account creation isn't exposed via a public endpoint yet (Stage 2). This logic instead needs a shared helper used by the migration script (Task 12) and, later in Stage 2, by a signup endpoint.
- Create: `backend/app/services/account.py`
- Test: `backend/tests/test_account_service.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_account_service.py
from app.models.client import Client
from app.models.user import AccountType, User
from app.services.account import create_account


def test_create_account_creates_one_implicit_client(db_session):
    user = create_account(
        db_session,
        email="basti@example.com",
        password="Grindcore123!",
        display_name="Basti",
        account_type=AccountType.COACH,
    )

    assert user.id is not None
    clients = db_session.query(Client).filter(Client.owner_id == user.id).all()
    assert len(clients) == 1
    assert clients[0].name == "Basti"


def test_create_account_hashes_password(db_session):
    user = create_account(
        db_session,
        email="basti@example.com",
        password="Grindcore123!",
        display_name="Basti",
        account_type=AccountType.SINGLE,
    )
    assert user.password_hash != "Grindcore123!"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_account_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.account'`

- [ ] **Step 3: Write `app/services/account.py`**

```python
"""
Account-Erstellung: legt einen User UND dessen automatisch mitgeliefertes
Client-Profil in einem Schritt an - siehe Design-Spec Abschnitt
"Kontotyp". Wird vom Migrationsscript (Stufe 1) und später vom
Self-Signup-Endpunkt (Stufe 2) gemeinsam genutzt.
"""
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.user import AccountType, User
from app.services.auth import hash_password


def create_account(
    db: Session,
    *,
    email: str,
    password: str,
    display_name: str,
    account_type: AccountType = AccountType.SINGLE,
) -> User:
    user = User(
        email=email,
        password_hash=hash_password(password),
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_account_service.py -v`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/account.py backend/tests/test_account_service.py
git commit -m "feat: add create_account service that auto-creates the implicit Client"
```

---

### Task 7: `client_id` on `Pose`, `DayLog`, `Photo` + composite unique constraints

This is the core data-isolation change from the spec. `Pose.name` and `DayLog.date` stop being globally unique and become unique *per client*.

**Files:**
- Modify: `backend/app/models/pose.py`
- Modify: `backend/app/models/day_log.py`
- Modify: `backend/app/models/photo.py`
- Test: `backend/tests/test_client_scoped_models.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_client_scoped_models.py
import pytest
from sqlalchemy.exc import IntegrityError

from app.models.client import Client
from app.models.day_log import DayLog
from app.models.pose import Pose
from app.models.user import User


def _make_two_clients(db_session):
    user = User(email="a@b.com", password_hash="x", display_name="A")
    db_session.add(user)
    db_session.flush()
    client_a = Client(owner_id=user.id, name="Kunde A")
    client_b = Client(owner_id=user.id, name="Kunde B")
    db_session.add_all([client_a, client_b])
    db_session.commit()
    return client_a, client_b


def test_two_clients_can_have_same_pose_name(db_session):
    client_a, client_b = _make_two_clients(db_session)
    db_session.add(Pose(client_id=client_a.id, name="Front Double Biceps", sort_order=0))
    db_session.add(Pose(client_id=client_b.id, name="Front Double Biceps", sort_order=0))
    db_session.commit()  # darf NICHT scheitern

    assert db_session.query(Pose).count() == 2


def test_same_client_cannot_have_duplicate_pose_name(db_session):
    client_a, _ = _make_two_clients(db_session)
    db_session.add(Pose(client_id=client_a.id, name="Front Double Biceps", sort_order=0))
    db_session.commit()

    db_session.add(Pose(client_id=client_a.id, name="Front Double Biceps", sort_order=1))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_two_clients_can_have_daylog_same_date(db_session):
    client_a, client_b = _make_two_clients(db_session)
    db_session.add(DayLog(client_id=client_a.id, date="2026-01-01", weight_kg=80))
    db_session.add(DayLog(client_id=client_b.id, date="2026-01-01", weight_kg=90))
    db_session.commit()  # darf NICHT scheitern

    assert db_session.query(DayLog).count() == 2


def test_same_client_cannot_have_duplicate_daylog_date(db_session):
    client_a, _ = _make_two_clients(db_session)
    db_session.add(DayLog(client_id=client_a.id, date="2026-01-01", weight_kg=80))
    db_session.commit()

    db_session.add(DayLog(client_id=client_a.id, date="2026-01-01", weight_kg=81))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_client_scoped_models.py -v`
Expected: FAIL with `TypeError: 'client_id' is an invalid keyword argument for Pose` (and similarly for `DayLog`)

- [ ] **Step 3: Update `app/models/pose.py`**

Replace the whole file:

```python
"""
Pose = eine frei konfigurierbare Körperhaltung/-perspektive
(z.B. "Front Double Biceps", "Side Chest", "Rear Lat Spread"), gehört zu
GENAU EINEM Client - jeder Kunde hat seine eigene, unabhängige Pose-Liste
(siehe Design-Spec Abschnitt "Datenmodell").

Start: 7 Standard-Posen pro neuem Client (siehe app/core/seed.py),
erweiterbar bis ~20 über die Einstellungsseite (Pose-CRUD-Router).
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Pose(Base):
    __tablename__ = "poses"
    __table_args__ = (UniqueConstraint("client_id", "name", name="uq_pose_client_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Steuert die Reihenfolge in Dropdowns/Grids; frei per Drag&Drop
    # änderbar (POC: einfach hochzählen bei Anlage).
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    photos: Mapped[list["Photo"]] = relationship(  # noqa: F821
        back_populates="pose"
    )

    def __repr__(self) -> str:
        return f"<Pose id={self.id} client_id={self.client_id} name={self.name!r}>"
```

- [ ] **Step 4: Update `app/models/day_log.py`**

Replace the whole file:

```python
"""
DayLog = Tagesdaten, die NICHT an ein einzelnes Bild gebunden sind, gehört
zu GENAU EINEM Client.

Wichtig gemäß Anforderung: Körpergewicht wird pro Datum UND Client
gespeichert, nicht pro Bild. Ein Tag kann pro Client beliebig viele Fotos
(verschiedener Posen) haben, aber genau einen DayLog-Eintrag.
"""
from datetime import date as date_, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DayLog(Base):
    __tablename__ = "day_logs"
    __table_args__ = (UniqueConstraint("client_id", "date", name="uq_daylog_client_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )

    date: Mapped[date_] = mapped_column(Date, nullable=False, index=True)

    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    photos: Mapped[list["Photo"]] = relationship(  # noqa: F821
        back_populates="day_log"
    )

    def __repr__(self) -> str:
        return f"<DayLog id={self.id} client_id={self.client_id} date={self.date} weight_kg={self.weight_kg}>"
```

- [ ] **Step 5: Add `client_id` to `app/models/photo.py`**

In `backend/app/models/photo.py`, add the import and the column. Change the import line:

```python
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
```

(unchanged — `ForeignKey` is already imported)

Add this field right after the `id` column (before `filename`):

```python
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
```

Update the module docstring's first line to mention the Client scope:

```python
"""
Photo = ein einzelnes Bild aus dem überwachten Ordner, gehört zu GENAU
EINEM Client.
```

(replace the old first two lines with this — keep the rest of the docstring as-is)

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_client_scoped_models.py -v`
Expected: `4 passed`

- [ ] **Step 7: Run the full test suite to check for regressions**

Run: `cd backend && .venv/Scripts/python -m pytest -v`
Expected: all tests from Tasks 1–6 still pass (they don't touch Pose/DayLog/Photo directly, so no regressions expected — this is a sanity check).

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/pose.py backend/app/models/day_log.py backend/app/models/photo.py backend/tests/test_client_scoped_models.py
git commit -m "feat: scope Pose/DayLog/Photo to client_id, make name/date unique per client"
```

---

### Task 8: Per-client pose seeding

`seed_default_poses` currently seeds once, globally, if the `poses` table is empty. It now needs to run per-client, at client creation.

**Files:**
- Modify: `backend/app/core/seed.py`
- Modify: `backend/app/routers/clients.py` (`create_client` calls it)
- Test: `backend/tests/test_clients_router.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_clients_router.py`:

```python
def test_creating_client_seeds_default_poses(client, db_session):
    _login(client, db_session)
    created = client.post("/api/clients", json={"name": "Max"}).json()

    from app.models.pose import Pose

    poses = db_session.query(Pose).filter(Pose.client_id == created["id"]).order_by(Pose.sort_order).all()
    assert len(poses) == 7
    assert poses[0].name == "Front Double Biceps"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_clients_router.py -v`
Expected: FAIL — `assert 0 == 7`

- [ ] **Step 3: Rewrite `app/core/seed.py`**

```python
"""Legt die 7 Standard-Posen für einen neu angelegten Client an."""
from sqlalchemy.orm import Session

from app.models.pose import Pose

DEFAULT_POSES = [
    "Front Double Biceps",
    "Front Lat Spread",
    "Side Chest",
    "Back Double Biceps",
    "Back Lat Spread",
    "Side Triceps",
    "Most Muscular",
]


def seed_default_poses_for_client(db: Session, client_id: int) -> None:
    for i, name in enumerate(DEFAULT_POSES):
        db.add(Pose(client_id=client_id, name=name, sort_order=i))
    db.commit()
```

(the old `seed_default_poses(db)` global-check function is fully replaced — nothing else calls it after this task and Task 12)

- [ ] **Step 4: Call it from `create_client`**

In `backend/app/routers/clients.py`, update the import and the `create_client` handler:

```python
from app.core.seed import seed_default_poses_for_client
```

```python
@router.post("", response_model=ClientOut, status_code=201)
def create_client(
    payload: ClientCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    client_row = Client(owner_id=current_user.id, **payload.model_dump())
    db.add(client_row)
    db.commit()
    db.refresh(client_row)
    seed_default_poses_for_client(db, client_row.id)
    return client_row
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_clients_router.py -v`
Expected: `5 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/seed.py backend/app/routers/clients.py backend/tests/test_clients_router.py
git commit -m "feat: seed default poses per-client instead of once globally"
```

---

### Task 9: Account-type toggle endpoint (`single` → `coach`)

**Files:**
- Modify: `backend/app/schemas/auth.py`
- Modify: `backend/app/routers/auth.py`
- Test: `backend/tests/test_auth_router.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_auth_router.py`:

```python
def test_switch_to_coach_flips_account_type(client, db_session):
    _make_user(db_session)
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})

    response = client.post("/api/auth/switch-to-coach")
    assert response.status_code == 200
    assert response.json()["account_type"] == "coach"

    me_response = client.get("/api/auth/me")
    assert me_response.json()["account_type"] == "coach"


def test_switch_to_coach_is_idempotent(client, db_session):
    _make_user(db_session)
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})
    client.post("/api/auth/switch-to-coach")
    second_response = client.post("/api/auth/switch-to-coach")
    assert second_response.status_code == 200
    assert second_response.json()["account_type"] == "coach"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_auth_router.py -v`
Expected: FAIL with 404 on `/api/auth/switch-to-coach`

- [ ] **Step 3: Add the endpoint to `app/routers/auth.py`**

```python
from app.models.user import AccountType


@router.post("/switch-to-coach", response_model=UserOut)
def switch_to_coach(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Kippt account_type auf `coach`. Legt KEINEN neuen Client an und
    verschiebt keine Daten - der implizite Client existiert seit
    Account-Erstellung bereits (siehe services/account.py), er wird nur
    im Dashboard sichtbar. Siehe Design-Spec Abschnitt "Kontotyp"."""
    current_user.account_type = AccountType.COACH
    db.commit()
    db.refresh(current_user)
    return current_user
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_auth_router.py -v`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/auth.py backend/tests/test_auth_router.py
git commit -m "feat: add switch-to-coach endpoint (pure account_type flip)"
```

---

### Task 10: `AppSetting` moves from global to per-account

**Files:**
- Modify: `backend/app/models/app_setting.py`
- Modify: `backend/app/services/ai_comparison.py` (`resolve_gemini_api_key` signature)
- Modify: `backend/app/routers/settings.py`
- Test: `backend/tests/test_settings_router.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_settings_router.py
from app.models.user import User
from app.services.auth import hash_password


def _login(client, db_session, email="a@b.com", password="pw12345"):
    user = User(email=email, password_hash=hash_password(password), display_name="A")
    db_session.add(user)
    db_session.commit()
    client.post("/api/auth/login", json={"email": email, "password": password})
    return user


def test_gemini_key_is_scoped_per_account(client, db_session):
    _login(client, db_session, email="a@b.com", password="pw12345")
    client.put("/api/settings/gemini-key", json={"api_key": "AIzaSyAAAA1111"})
    status_a = client.get("/api/settings/gemini-key").json()
    assert status_a["configured"] is True
    assert status_a["last4"] == "1111"
    client.post("/api/auth/logout")

    _login(client, db_session, email="c@d.com", password="pw67890")
    status_c = client.get("/api/settings/gemini-key").json()
    assert status_c["configured"] is False


def test_gemini_key_requires_login(client, db_session):
    response = client.get("/api/settings/gemini-key")
    assert response.status_code == 401


def test_display_settings_scoped_per_account(client, db_session):
    _login(client, db_session, email="a@b.com", password="pw12345")
    client.put("/api/settings/display", json={"timeline_columns_max": 3, "timeline_weeks_per_page": 4})
    result = client.get("/api/settings/display").json()
    assert result["timeline_columns_max"] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_settings_router.py -v`
Expected: FAIL — currently `/api/settings/*` has no auth requirement and one global key, so `status_c["configured"]` would incorrectly be `True`.

- [ ] **Step 3: Add `owner_id` to `app/models/app_setting.py`**

Replace the whole file:

```python
"""
AppSetting = simples Key-Value-Store für Account-Einstellungen (Gemini-
API-Key, Anzeige-Präferenzen). Hängt an owner_id (User) statt global -
siehe Design-Spec Abschnitt "AppSetting wandert zum Account". Der
Primärschlüssel ist jetzt das Paar (owner_id, key) statt nur key, damit
zwei Accounts denselben Settings-Key (z.B. "gemini_api_key") unabhängig
voneinander belegen können.
"""
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AppSetting(Base):
    __tablename__ = "app_settings"

    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str | None] = mapped_column(String(2000), nullable=True)
```

- [ ] **Step 4: Update `resolve_gemini_api_key` to take an `owner_id`**

In `backend/app/services/ai_comparison.py`, find `resolve_gemini_api_key` (around line 123) and change its signature and query:

```python
def resolve_gemini_api_key(db: Session, owner_id: int) -> tuple[str | None, str | None]:
    """Liefert (key, source) - DB-Wert (source="settings") hat Vorrang vor
    GEMINI_API_KEY aus .env (source="env"). (None, None) wenn nichts gesetzt."""
    setting = (
        db.query(AppSetting)
        .filter(AppSetting.owner_id == owner_id, AppSetting.key == GEMINI_KEY_SETTING)
        .first()
    )
```

(keep the rest of the function body identical — only the `db.get(AppSetting, GEMINI_KEY_SETTING)` line becomes the query above; everything after that `if setting and setting.value:` stays the same)

Also update the call site inside the same file (`compare_photos`, where `resolve_gemini_api_key(db)` is called) — this now needs an `owner_id` parameter threaded through. Find the `compare_photos` function signature and add `owner_id: int` as a parameter, then pass it to `resolve_gemini_api_key(db, owner_id)`.

- [ ] **Step 5: Update `resolve_gemini_api_key` callers in `comparisons.py`**

`backend/app/routers/comparisons.py` calls `compare_photos(...)` and `compare_photos_all(...)` — both now need `owner_id=current_user.id` added to their call kwargs. This router is fully rewritten in Task 12 (client-scoping), so leave the exact wiring for that task — for now, just confirm `ai_comparison.py`'s two public functions (`compare_photos`, `compare_photos_all`) both accept and use `owner_id` consistently.

- [ ] **Step 6: Rewrite `app/routers/settings.py`**

Replace the whole file:

```python
"""
Account-Einstellungen: Gemini-API-Key und Anzeige-Präferenzen, beide
gebunden an den eingeloggten Account (nicht mehr global, nicht pro
Kunde) - siehe Design-Spec Abschnitt "AppSetting wandert zum Account".
"""
import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.app_setting import AppSetting
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.settings import DisplaySettings, GeminiKeyIn, GeminiKeyStatus
from app.services.ai_comparison import GEMINI_KEY_SETTING, resolve_gemini_api_key

router = APIRouter(prefix="/api/settings", tags=["settings"])

DISPLAY_SETTINGS_KEY = "display_settings"


@router.get("/gemini-key", response_model=GeminiKeyStatus)
def get_gemini_key_status(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> GeminiKeyStatus:
    key, source = resolve_gemini_api_key(db, current_user.id)
    if not key:
        return GeminiKeyStatus(configured=False)
    return GeminiKeyStatus(configured=True, source=source, last4=key[-4:])


@router.put("/gemini-key", response_model=GeminiKeyStatus)
def set_gemini_key(
    payload: GeminiKeyIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GeminiKeyStatus:
    value = payload.api_key.strip()
    setting = db.get(AppSetting, (current_user.id, GEMINI_KEY_SETTING))
    if setting is None:
        setting = AppSetting(owner_id=current_user.id, key=GEMINI_KEY_SETTING, value=value)
        db.add(setting)
    else:
        setting.value = value
    db.commit()
    return GeminiKeyStatus(configured=True, source="settings", last4=value[-4:])


@router.delete("/gemini-key", status_code=204)
def clear_gemini_key(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    setting = db.get(AppSetting, (current_user.id, GEMINI_KEY_SETTING))
    if setting is not None:
        db.delete(setting)
        db.commit()


@router.get("/display", response_model=DisplaySettings)
def get_display_settings(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> DisplaySettings:
    setting = db.get(AppSetting, (current_user.id, DISPLAY_SETTINGS_KEY))
    if not setting or not setting.value:
        return DisplaySettings()
    try:
        return DisplaySettings(**json.loads(setting.value))
    except (json.JSONDecodeError, TypeError):
        return DisplaySettings()


@router.put("/display", response_model=DisplaySettings)
def set_display_settings(
    payload: DisplaySettings,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DisplaySettings:
    clamped = DisplaySettings(
        timeline_columns_max=max(1, min(10, payload.timeline_columns_max)),
        timeline_weeks_per_page=max(1, min(25, payload.timeline_weeks_per_page)),
    )
    value = json.dumps(clamped.model_dump())
    setting = db.get(AppSetting, (current_user.id, DISPLAY_SETTINGS_KEY))
    if setting is None:
        setting = AppSetting(owner_id=current_user.id, key=DISPLAY_SETTINGS_KEY, value=value)
        db.add(setting)
    else:
        setting.value = value
    db.commit()
    return clamped
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_settings_router.py -v`
Expected: `3 passed`

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/app_setting.py backend/app/services/ai_comparison.py backend/app/routers/settings.py backend/tests/test_settings_router.py
git commit -m "feat: scope AppSetting (Gemini key, display prefs) to owner_id instead of global"
```

---

### Task 11: File storage helper for client-scoped paths

Before rewriting the photos/poses/day_logs/comparisons routers to be client-scoped (Task 12), extract the path-construction logic into small, testable helpers, per the spec's "Dateiablage" section (`<client_id>/<datum>/<dateiname>` etc.).

**Files:**
- Create: `backend/app/services/storage_paths.py`
- Test: `backend/tests/test_storage_paths.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_storage_paths.py
from pathlib import PurePosixPath

from app.services.storage_paths import (
    incoming_dir_for_client,
    normalized_dir_for_client_pose,
    processed_dir_for_client_date,
)


def test_incoming_dir_includes_client_id():
    result = incoming_dir_for_client(client_id=7)
    assert PurePosixPath(result).name == "7"
    assert "photos_incoming" in result.as_posix()


def test_processed_dir_includes_client_id_and_date():
    result = processed_dir_for_client_date(client_id=7, date_str="2026-01-01")
    parts = result.as_posix().split("/")
    assert "7" in parts
    assert "2026-01-01" in parts
    assert parts.index("7") < parts.index("2026-01-01")


def test_normalized_dir_includes_client_and_pose():
    result = normalized_dir_for_client_pose(client_id=7, pose_id=3)
    parts = result.as_posix().split("/")
    assert "7" in parts
    assert "3" in parts
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_storage_paths.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `app/services/storage_paths.py`**

```python
"""
Zentrale Pfad-Konstruktion für client-gescopte Dateiablage - siehe
Design-Spec Abschnitt "Dateiablage". Jede Datei-Operation in
routers/photos.py und services/folder_sync.py geht durch diese
Funktionen, statt Pfade selbst zusammenzubauen - das ist die zentrale
Stelle, die bei einem späteren Umstieg auf Object-Storage (Stufe 3)
ausgetauscht werden müsste.
"""
from pathlib import Path

from app.core.config import settings


def incoming_dir_for_client(client_id: int) -> Path:
    return settings.photos_incoming_dir / str(client_id)


def processed_dir_for_client_date(client_id: int, date_str: str) -> Path:
    return settings.photos_processed_dir / str(client_id) / date_str


def normalized_dir_for_client_pose(client_id: int, pose_id: int) -> Path:
    return settings.photos_normalized_dir / str(client_id) / str(pose_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_storage_paths.py -v`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/storage_paths.py backend/tests/test_storage_paths.py
git commit -m "feat: add client-scoped storage path helpers"
```

---

### Task 12: Client-scope the `photos`, `poses`, `day_logs`, `comparisons` routers

This is the biggest single task: every route in these four routers moves under `/api/clients/{client_id}/...` and gets `client_id` filtering, using `get_owned_client` from Task 5. `folder_sync.py` (used by `/sync` and `/upload`) also needs a `client_id` parameter.

**Files:**
- Modify: `backend/app/routers/poses.py`
- Modify: `backend/app/routers/day_logs.py`
- Modify: `backend/app/routers/photos.py`
- Modify: `backend/app/routers/comparisons.py`
- Modify: `backend/app/services/folder_sync.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_poses_router_scoped.py`, `backend/tests/test_day_logs_router_scoped.py`

- [ ] **Step 1: Write the failing test for poses**

```python
# backend/tests/test_poses_router_scoped.py
from app.models.user import User
from app.services.auth import hash_password


def _login_and_get_client(client, db_session, email="a@b.com", password="pw12345"):
    user = User(email=email, password_hash=hash_password(password), display_name="A")
    db_session.add(user)
    db_session.commit()
    client.post("/api/auth/login", json={"email": email, "password": password})
    created = client.post("/api/clients", json={"name": "Kunde"}).json()
    return created["id"]


def test_poses_are_scoped_to_client(client, db_session):
    client_id_a = _login_and_get_client(client, db_session, email="a@b.com", password="pw12345")
    poses_a = client.get(f"/api/clients/{client_id_a}/poses").json()
    assert len(poses_a) == 7  # Default-Seed
    client.post("/api/auth/logout")

    client_id_b = _login_and_get_client(client, db_session, email="c@d.com", password="pw67890")
    poses_b = client.get(f"/api/clients/{client_id_b}/poses").json()
    assert len(poses_b) == 7
    assert poses_a[0]["id"] != poses_b[0]["id"]


def test_cannot_list_poses_of_foreign_client(client, db_session):
    client_id_a = _login_and_get_client(client, db_session, email="a@b.com", password="pw12345")
    client.post("/api/auth/logout")
    _login_and_get_client(client, db_session, email="c@d.com", password="pw67890")

    response = client.get(f"/api/clients/{client_id_a}/poses")
    assert response.status_code == 404


def test_create_pose_scoped_to_client(client, db_session):
    client_id = _login_and_get_client(client, db_session)
    response = client.post(
        f"/api/clients/{client_id}/poses", json={"name": "Custom Pose"}
    )
    assert response.status_code == 201
    poses = client.get(f"/api/clients/{client_id}/poses").json()
    assert any(p["name"] == "Custom Pose" for p in poses)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_poses_router_scoped.py -v`
Expected: FAIL with 404s on `/api/clients/{id}/poses`

- [ ] **Step 3: Rewrite `app/routers/poses.py`**

```python
"""Posen-Konfiguration pro Kunde: anlegen, umbenennen, löschen."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.client import Client
from app.models.pose import Pose
from app.routers.clients import get_owned_client
from app.schemas.pose import PoseCreate, PoseOut, PoseUpdate

router = APIRouter(prefix="/api/clients/{client_id}/poses", tags=["poses"])


@router.get("", response_model=list[PoseOut])
def list_poses(client_row: Client = Depends(get_owned_client), db: Session = Depends(get_db)):
    return (
        db.query(Pose)
        .filter(Pose.client_id == client_row.id)
        .order_by(Pose.sort_order, Pose.id)
        .all()
    )


@router.post("", response_model=PoseOut, status_code=201)
def create_pose(
    payload: PoseCreate, client_row: Client = Depends(get_owned_client), db: Session = Depends(get_db)
):
    exists = (
        db.query(Pose)
        .filter(Pose.client_id == client_row.id, func.lower(Pose.name) == payload.name.lower())
        .first()
    )
    if exists:
        raise HTTPException(409, "Pose mit diesem Namen existiert bereits")
    max_order = (
        db.query(func.max(Pose.sort_order)).filter(Pose.client_id == client_row.id).scalar() or 0
    )
    pose = Pose(client_id=client_row.id, name=payload.name, sort_order=max_order + 1)
    db.add(pose)
    db.commit()
    db.refresh(pose)
    return pose


def _get_owned_pose(pose_id: int, client_row: Client, db: Session) -> Pose:
    pose = db.query(Pose).filter(Pose.id == pose_id, Pose.client_id == client_row.id).first()
    if not pose:
        raise HTTPException(404, "Pose nicht gefunden")
    return pose


@router.patch("/{pose_id}", response_model=PoseOut)
def update_pose(
    pose_id: int,
    payload: PoseUpdate,
    client_row: Client = Depends(get_owned_client),
    db: Session = Depends(get_db),
):
    pose = _get_owned_pose(pose_id, client_row, db)
    if payload.name is not None:
        pose.name = payload.name
    if payload.sort_order is not None:
        pose.sort_order = payload.sort_order
    db.commit()
    db.refresh(pose)
    return pose


@router.delete("/{pose_id}", status_code=204)
def delete_pose(
    pose_id: int, client_row: Client = Depends(get_owned_client), db: Session = Depends(get_db)
):
    pose = _get_owned_pose(pose_id, client_row, db)
    # Fotos bleiben erhalten, pose_id wird via ondelete=SET NULL genullt
    # -> Bilder landen wieder im "Unprocessed"-Filter für diese Pose.
    db.delete(pose)
    db.commit()
```

- [ ] **Step 4: Run poses tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_poses_router_scoped.py -v`
Expected: `3 passed`

- [ ] **Step 5: Write the failing test for day_logs**

```python
# backend/tests/test_day_logs_router_scoped.py
from app.models.user import User
from app.services.auth import hash_password


def _login_and_get_client(client, db_session, email="a@b.com", password="pw12345"):
    user = User(email=email, password_hash=hash_password(password), display_name="A")
    db_session.add(user)
    db_session.commit()
    client.post("/api/auth/login", json={"email": email, "password": password})
    created = client.post("/api/clients", json={"name": "Kunde"}).json()
    return created["id"]


def test_daylogs_scoped_to_client(client, db_session):
    client_id_a = _login_and_get_client(client, db_session, email="a@b.com", password="pw12345")
    client.put(f"/api/clients/{client_id_a}/day-logs", json={"date": "2026-01-01", "weight_kg": 80})
    client.post("/api/auth/logout")

    client_id_b = _login_and_get_client(client, db_session, email="c@d.com", password="pw67890")
    put_resp = client.put(
        f"/api/clients/{client_id_b}/day-logs", json={"date": "2026-01-01", "weight_kg": 90}
    )
    assert put_resp.status_code == 200  # gleiches Datum, anderer Client - darf nicht kollidieren

    logs_b = client.get(f"/api/clients/{client_id_b}/day-logs").json()
    assert len(logs_b) == 1
    assert logs_b[0]["weight_kg"] == 90


def test_cannot_access_foreign_client_daylogs(client, db_session):
    client_id_a = _login_and_get_client(client, db_session, email="a@b.com", password="pw12345")
    client.post("/api/auth/logout")
    _login_and_get_client(client, db_session, email="c@d.com", password="pw67890")

    response = client.get(f"/api/clients/{client_id_a}/day-logs")
    assert response.status_code == 404
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_day_logs_router_scoped.py -v`
Expected: FAIL with 404s (route doesn't exist under `/api/clients/{id}/day-logs` yet)

- [ ] **Step 7: Rewrite `app/routers/day_logs.py`**

```python
"""Tagesdaten (aktuell nur Gewicht) pro Kunde."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.client import Client
from app.models.day_log import DayLog
from app.routers.clients import get_owned_client
from app.schemas.day_log import DayLogOut, DayLogUpsert

router = APIRouter(prefix="/api/clients/{client_id}/day-logs", tags=["day-logs"])


@router.get("", response_model=list[DayLogOut])
def list_day_logs(client_row: Client = Depends(get_owned_client), db: Session = Depends(get_db)):
    return (
        db.query(DayLog)
        .filter(DayLog.client_id == client_row.id)
        .order_by(DayLog.date.desc())
        .all()
    )


@router.put("", response_model=DayLogOut)
def upsert_day_log(
    payload: DayLogUpsert,
    client_row: Client = Depends(get_owned_client),
    db: Session = Depends(get_db),
):
    """Legt den DayLog für ein Datum an oder aktualisiert ihn (Gewicht/Notizen)."""
    day_log = (
        db.query(DayLog)
        .filter(DayLog.client_id == client_row.id, DayLog.date == payload.date)
        .first()
    )
    if day_log is None:
        day_log = DayLog(client_id=client_row.id, date=payload.date)
        db.add(day_log)
    day_log.weight_kg = payload.weight_kg
    day_log.notes = payload.notes
    db.commit()
    db.refresh(day_log)
    return day_log
```

- [ ] **Step 8: Run day_logs tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_day_logs_router_scoped.py -v`
Expected: `2 passed`

- [ ] **Step 9: Update `folder_sync.py` to accept `client_id`**

`backend/app/services/folder_sync.py`'s `sync_incoming_folder(db)` currently scans the single global `settings.photos_incoming_dir`. Read the current file first (`cat backend/app/services/folder_sync.py`) to confirm exact line numbers before editing — the shape below is what every occurrence of `settings.photos_incoming_dir` / `settings.photos_processed_dir` / `Photo(...)` construction becomes:

- Change the function signature: `def sync_incoming_folder(db: Session, client_id: int) -> list[Photo]:`
- Replace every `settings.photos_incoming_dir` reference inside it with `incoming_dir_for_client(client_id)` (import from `app.services.storage_paths`)
- Every `Photo(...)` construction inside the function gets `client_id=client_id` added as a kwarg
- The `_backfill_missing_previews` helper takes the same `client_id` parameter and filters its query by `Photo.client_id == client_id` in addition to the existing `Photo.status == ProcessingStatus.UNPROCESSED` filter

- [ ] **Step 10: Write the failing test for photos**

```python
# backend/tests/test_photos_router_scoped.py
from app.models.user import User
from app.services.auth import hash_password


def _login_and_get_client(client, db_session, email="a@b.com", password="pw12345"):
    user = User(email=email, password_hash=hash_password(password), display_name="A")
    db_session.add(user)
    db_session.commit()
    client.post("/api/auth/login", json={"email": email, "password": password})
    created = client.post("/api/clients", json={"name": "Kunde"}).json()
    return created["id"]


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
```

- [ ] **Step 11: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_photos_router_scoped.py -v`
Expected: FAIL with 404s (routes still at old `/api/photos/*` paths)

- [ ] **Step 12: Rewrite `app/routers/photos.py`**

Apply these changes to the existing file (shown as the new state of each affected piece — keep everything else, e.g. `_delete_photo_files`, `_assign_photo`'s docstring, unchanged in spirit):

Change the router prefix and imports at the top:

```python
from app.core.config import settings
from app.core.database import get_db
from app.models.client import Client
from app.models.day_log import DayLog
from app.models.photo import Photo, ProcessingStatus
from app.models.pose import Pose
from app.routers.clients import get_owned_client
from app.schemas.photo import (
    PhotoAssign,
    PhotoBulkAssign,
    PhotoOut,
    PhotoRepose,
    PhotoUnprocessedOut,
)
from app.services.folder_sync import sync_incoming_folder
from app.services.pose_normalization import normalize_photo
from app.services.pose_suggestion import compute_pose_suggestions
from app.services.storage_paths import normalized_dir_for_client_pose, processed_dir_for_client_date
from app.services.thumbnails import generate_thumbnail, thumbnail_path_for

router = APIRouter(prefix="/api/clients/{client_id}/photos", tags=["photos"])
```

Every route handler gets `client_row: Client = Depends(get_owned_client)` added as a parameter, and every DB query gets an added `.filter(Photo.client_id == client_row.id)`:

```python
@router.post("/sync", response_model=list[PhotoOut])
def sync_photos(client_row: Client = Depends(get_owned_client), db: Session = Depends(get_db)):
    return sync_incoming_folder(db, client_row.id)


@router.post("/upload", response_model=list[PhotoOut])
def upload_photos(
    files: list[UploadFile],
    client_row: Client = Depends(get_owned_client),
    db: Session = Depends(get_db),
):
    from app.services.storage_paths import incoming_dir_for_client

    incoming_dir = incoming_dir_for_client(client_row.id)
    incoming_dir.mkdir(parents=True, exist_ok=True)
    saved_any = False
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
        saved_any = True

    if not saved_any:
        raise HTTPException(400, "Keine gültigen Bilddateien im Upload gefunden")

    return sync_incoming_folder(db, client_row.id)


@router.get("/unprocessed", response_model=list[PhotoUnprocessedOut])
def list_unprocessed(client_row: Client = Depends(get_owned_client), db: Session = Depends(get_db)):
    photos = (
        db.query(Photo)
        .filter(Photo.client_id == client_row.id, Photo.status == ProcessingStatus.UNPROCESSED)
        .order_by(Photo.taken_at)
        .all()
    )
    suggestions = compute_pose_suggestions(db, photos)
    result = []
    for photo in photos:
        out = PhotoUnprocessedOut.model_validate(photo)
        out.suggested_pose_id = suggestions.get(photo.id)
        result.append(out)
    return result


@router.get("", response_model=list[PhotoOut])
def list_photos(
    pose_id: int | None = None,
    status: ProcessingStatus | None = None,
    client_row: Client = Depends(get_owned_client),
    db: Session = Depends(get_db),
):
    q = db.query(Photo).filter(Photo.client_id == client_row.id)
    if pose_id is not None:
        q = q.filter(Photo.pose_id == pose_id)
    if status is not None:
        q = q.filter(Photo.status == status)
    return q.order_by(Photo.taken_at.desc()).all()


@router.post("/renormalize-all", response_model=list[PhotoOut])
def renormalize_all(client_row: Client = Depends(get_owned_client), db: Session = Depends(get_db)):
    photos = (
        db.query(Photo)
        .filter(Photo.client_id == client_row.id, Photo.pose_id.isnot(None))
        .all()
    )
    for photo in photos:
        src = settings.data_dir / (photo.preview_path or photo.original_path)
        if not src.exists():
            continue
        dest = normalized_dir_for_client_pose(client_row.id, photo.pose_id) / f"{photo.id}.jpg"
        result = normalize_photo(src, dest)
        if result.success and result.normalized_path:
            photo.normalized_path = result.normalized_path.relative_to(settings.data_dir).as_posix()
            photo.landmarks_json = result.landmarks_json
            photo.status = ProcessingStatus.PROCESSED
        else:
            photo.status = ProcessingStatus.NORMALIZATION_FAILED
    db.commit()
    for p in photos:
        db.refresh(p)
    return photos


@router.post("/backfill-thumbnails")
def backfill_thumbnails(
    force: bool = False,
    client_row: Client = Depends(get_owned_client),
    db: Session = Depends(get_db),
) -> dict:
    query = db.query(Photo).filter(Photo.client_id == client_row.id)
    if not force:
        query = query.filter(Photo.thumbnail_path.is_(None))
    photos = query.all()
    generated = 0
    for photo in photos:
        source = settings.data_dir / (photo.preview_path or photo.original_path)
        if not source.exists():
            continue
        dest = thumbnail_path_for(source)
        if generate_thumbnail(source, dest):
            photo.thumbnail_path = dest.relative_to(settings.data_dir).as_posix()
            generated += 1
    db.commit()
    return {"total_candidates": len(photos), "generated": generated}
```

`_assign_photo` gains a `client_id` parameter and uses the new path helpers instead of the old global ones:

```python
def _assign_photo(db: Session, photo: Photo, pose: Pose, weight_kg: float | None) -> Photo:
    day_date = photo.taken_at.date()
    day_log = (
        db.query(DayLog)
        .filter(DayLog.client_id == photo.client_id, DayLog.date == day_date)
        .first()
    )
    if day_log is None:
        day_log = DayLog(client_id=photo.client_id, date=day_date)
        db.add(day_log)
        db.flush()
    if weight_kg is not None:
        day_log.weight_kg = weight_kg

    src = settings.data_dir / photo.original_path
    dest_dir = processed_dir_for_client_date(photo.client_id, day_date.isoformat())
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / photo.filename
    if src.exists():
        shutil.move(str(src), str(dest))
        photo.original_path = dest.relative_to(settings.data_dir).as_posix()

    if photo.preview_path:
        preview_src = settings.data_dir / photo.preview_path
        if preview_src.exists():
            preview_dest = dest_dir / preview_src.name
            shutil.move(str(preview_src), str(preview_dest))
            photo.preview_path = preview_dest.relative_to(settings.data_dir).as_posix()

    if photo.thumbnail_path:
        thumb_src = settings.data_dir / photo.thumbnail_path
        if thumb_src.exists():
            thumb_dest = dest_dir / thumb_src.name
            shutil.move(str(thumb_src), str(thumb_dest))
            photo.thumbnail_path = thumb_dest.relative_to(settings.data_dir).as_posix()
    if not photo.thumbnail_path:
        thumb_source = settings.data_dir / (photo.preview_path or photo.original_path)
        thumb_dest = dest_dir / thumbnail_path_for(thumb_source).name
        if generate_thumbnail(thumb_source, thumb_dest):
            photo.thumbnail_path = thumb_dest.relative_to(settings.data_dir).as_posix()

    photo.pose_id = pose.id
    photo.day_log_id = day_log.id
    photo.status = ProcessingStatus.PROCESSED
    photo.updated_at = datetime.utcnow()

    db.commit()

    normalize_source = settings.data_dir / (photo.preview_path or photo.original_path)
    normalized_dest = normalized_dir_for_client_pose(photo.client_id, pose.id) / f"{photo.id}.jpg"
    result = normalize_photo(normalize_source, normalized_dest)
    if result.success and result.normalized_path:
        photo.normalized_path = result.normalized_path.relative_to(settings.data_dir).as_posix()
        photo.landmarks_json = result.landmarks_json
    else:
        photo.status = ProcessingStatus.NORMALIZATION_FAILED

    db.commit()
    db.refresh(photo)
    return photo
```

The remaining handlers (`assign_photos_bulk`, `assign_photo`, `delete_photos_by_date`, `delete_photo`, `change_photo_pose`) each get `client_row: Client = Depends(get_owned_client)` added and every `db.query(Photo)...` / `db.get(Photo, photo_id)` gets a `Photo.client_id == client_row.id` filter added (for `db.get`, replace with an explicit filtered query since `db.get` only takes a primary key):

```python
@router.post("/assign-bulk", response_model=list[PhotoOut])
def assign_photos_bulk(
    payload: PhotoBulkAssign,
    client_row: Client = Depends(get_owned_client),
    db: Session = Depends(get_db),
):
    results: list[Photo] = []
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
        results.append(_assign_photo(db, photo, pose, item.weight_kg))
    return results


@router.post("/{photo_id}/assign", response_model=PhotoOut)
def assign_photo(
    photo_id: int,
    payload: PhotoAssign,
    client_row: Client = Depends(get_owned_client),
    db: Session = Depends(get_db),
):
    photo = db.query(Photo).filter(Photo.id == photo_id, Photo.client_id == client_row.id).first()
    if not photo:
        raise HTTPException(404, "Foto nicht gefunden")

    pose = db.query(Pose).filter(Pose.id == payload.pose_id, Pose.client_id == client_row.id).first()
    if not pose:
        raise HTTPException(404, "Pose nicht gefunden")

    return _assign_photo(db, photo, pose, payload.weight_kg)


@router.delete("/by-date/{date}", status_code=200)
def delete_photos_by_date(
    date: date_, client_row: Client = Depends(get_owned_client), db: Session = Depends(get_db)
):
    photos = (
        db.query(Photo)
        .filter(Photo.client_id == client_row.id)
        .filter(Photo.taken_at >= date)
        .filter(Photo.taken_at < date.fromordinal(date.toordinal() + 1))
        .all()
    )
    for photo in photos:
        _delete_photo_files(photo)
        db.delete(photo)
    db.commit()
    return {"deleted": len(photos)}


@router.delete("/{photo_id}", status_code=204)
def delete_photo(
    photo_id: int, client_row: Client = Depends(get_owned_client), db: Session = Depends(get_db)
):
    photo = db.query(Photo).filter(Photo.id == photo_id, Photo.client_id == client_row.id).first()
    if not photo:
        raise HTTPException(404, "Foto nicht gefunden")

    _delete_photo_files(photo)
    db.delete(photo)
    db.commit()


@router.patch("/{photo_id}/pose", response_model=PhotoOut)
def change_photo_pose(
    photo_id: int,
    payload: PhotoRepose,
    client_row: Client = Depends(get_owned_client),
    db: Session = Depends(get_db),
):
    photo = db.query(Photo).filter(Photo.id == photo_id, Photo.client_id == client_row.id).first()
    if not photo:
        raise HTTPException(404, "Foto nicht gefunden")

    pose = db.query(Pose).filter(Pose.id == payload.pose_id, Pose.client_id == client_row.id).first()
    if not pose:
        raise HTTPException(404, "Pose nicht gefunden")

    if photo.pose_id == pose.id:
        return photo

    old_normalized = settings.data_dir / photo.normalized_path if photo.normalized_path else None

    photo.pose_id = pose.id
    photo.updated_at = datetime.utcnow()

    normalize_source = settings.data_dir / (photo.preview_path or photo.original_path)
    normalized_dest = normalized_dir_for_client_pose(client_row.id, pose.id) / f"{photo.id}.jpg"
    result = normalize_photo(normalize_source, normalized_dest)
    if result.success and result.normalized_path:
        photo.normalized_path = result.normalized_path.relative_to(settings.data_dir).as_posix()
        photo.landmarks_json = result.landmarks_json
        photo.status = ProcessingStatus.PROCESSED
    else:
        photo.normalized_path = None
        photo.status = ProcessingStatus.NORMALIZATION_FAILED

    db.commit()
    db.refresh(photo)

    if old_normalized and old_normalized.exists():
        old_normalized.unlink()

    return photo
```

Keep `_delete_photo_files` exactly as-is (it operates on an already-loaded `Photo` object, no query to scope).

- [ ] **Step 13: Run photos tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_photos_router_scoped.py -v`
Expected: `3 passed`

- [ ] **Step 14: Rewrite `app/routers/comparisons.py`**

```python
"""
Comparison-Mode pro Kunde: liefert für eine Pose + zwei Daten die
passenden Fotos für Side-by-Side-/Overlay-Ansicht, sowie die optionale
KI-Judge-Analyse.
"""
from datetime import date as date_
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.client import Client
from app.models.day_log import DayLog
from app.models.photo import Photo
from app.models.pose import Pose
from app.routers.auth import get_current_user
from app.routers.clients import get_owned_client
from app.models.user import User
from app.schemas.photo import PhotoOut
from app.services.ai_comparison import AiComparisonError, compare_photos, compare_photos_all

router = APIRouter(prefix="/api/clients/{client_id}/comparisons", tags=["comparisons"])


def _find_photo(db: Session, client_id: int, pose_id: int, target_date: date_) -> Photo | None:
    return (
        db.query(Photo)
        .filter(Photo.client_id == client_id)
        .filter(Photo.pose_id == pose_id)
        .filter(Photo.taken_at >= target_date)
        .filter(Photo.taken_at < target_date.fromordinal(target_date.toordinal() + 1))
        .first()
    )


@router.get("")
def compare(
    pose_id: int = Query(...),
    date_x: date_ = Query(...),
    date_y: date_ = Query(...),
    client_row: Client = Depends(get_owned_client),
    db: Session = Depends(get_db),
) -> dict[str, PhotoOut | None]:
    photo_x = _find_photo(db, client_row.id, pose_id, date_x)
    photo_y = _find_photo(db, client_row.id, pose_id, date_y)
    if not photo_x or not photo_y:
        raise HTTPException(404, "Für mindestens eines der Daten existiert kein Foto dieser Pose")
    return {
        "photo_x": PhotoOut.model_validate(photo_x),
        "photo_y": PhotoOut.model_validate(photo_y),
    }


@router.get("/ai-analysis")
def ai_analysis(
    pose_id: int = Query(...),
    date_x: date_ = Query(...),
    date_y: date_ = Query(...),
    client_row: Client = Depends(get_owned_client),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    photo_x = _find_photo(db, client_row.id, pose_id, date_x)
    photo_y = _find_photo(db, client_row.id, pose_id, date_y)
    if not photo_x or not photo_y:
        raise HTTPException(404, "Für mindestens eines der Daten existiert kein Foto dieser Pose")

    pose = db.query(Pose).filter(Pose.id == pose_id, Pose.client_id == client_row.id).first()
    pose_name = pose.name if pose else "Unbekannte Pose"

    path_x = settings.data_dir / (photo_x.normalized_path or photo_x.preview_path or photo_x.original_path)
    path_y = settings.data_dir / (photo_y.normalized_path or photo_y.preview_path or photo_y.original_path)

    day_log_x = db.query(DayLog).filter(DayLog.client_id == client_row.id, DayLog.date == date_x).first()
    day_log_y = db.query(DayLog).filter(DayLog.client_id == client_row.id, DayLog.date == date_y).first()

    try:
        analysis = compare_photos(
            db=db,
            owner_id=current_user.id,
            path_x=path_x,
            path_y=path_y,
            pose_name=pose_name,
            date_x=date_x,
            date_y=date_y,
            weight_x=day_log_x.weight_kg if day_log_x else None,
            weight_y=day_log_y.weight_kg if day_log_y else None,
        )
    except AiComparisonError as exc:
        raise HTTPException(502, str(exc)) from exc

    return {"analysis": analysis}


@router.get("/ai-analysis-all")
def ai_analysis_all(
    date_x: date_ = Query(...),
    date_y: date_ = Query(...),
    client_row: Client = Depends(get_owned_client),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    poses = db.query(Pose).filter(Pose.client_id == client_row.id).order_by(Pose.sort_order, Pose.id).all()

    pairs: list[tuple[str, Path, Path]] = []
    for pose in poses:
        photo_x = _find_photo(db, client_row.id, pose.id, date_x)
        photo_y = _find_photo(db, client_row.id, pose.id, date_y)
        if not photo_x or not photo_y:
            continue
        path_x = settings.data_dir / (photo_x.normalized_path or photo_x.preview_path or photo_x.original_path)
        path_y = settings.data_dir / (photo_y.normalized_path or photo_y.preview_path or photo_y.original_path)
        pairs.append((pose.name, path_x, path_y))

    if not pairs:
        raise HTTPException(404, "Für keine Pose existieren Fotos an beiden gewählten Terminen")

    day_log_x = db.query(DayLog).filter(DayLog.client_id == client_row.id, DayLog.date == date_x).first()
    day_log_y = db.query(DayLog).filter(DayLog.client_id == client_row.id, DayLog.date == date_y).first()

    try:
        analysis = compare_photos_all(
            db=db,
            owner_id=current_user.id,
            pairs=pairs,
            date_x=date_x,
            date_y=date_y,
            weight_x=day_log_x.weight_kg if day_log_x else None,
            weight_y=day_log_y.weight_kg if day_log_y else None,
        )
    except AiComparisonError as exc:
        raise HTTPException(502, str(exc)) from exc

    return {"analysis": analysis}
```

Now go back to `backend/app/services/ai_comparison.py` and add `owner_id: int` as a parameter to `compare_photos_all` too (same pattern as `compare_photos` from Step 4), threading it into its own internal `resolve_gemini_api_key(db, owner_id)` call.

- [ ] **Step 15: Update router registration in `main.py`**

The prefixes changed, but `include_router` calls stay the same (FastAPI reads the prefix from each router object) — no change needed in `main.py` beyond what Tasks 4/5 already added.

- [ ] **Step 16: Run the full backend test suite**

Run: `cd backend && .venv/Scripts/python -m pytest -v`
Expected: all tests pass. Fix any import errors or stale references surfaced here before moving on.

- [ ] **Step 17: Commit**

```bash
git add backend/app/routers/poses.py backend/app/routers/day_logs.py backend/app/routers/photos.py backend/app/routers/comparisons.py backend/app/services/folder_sync.py backend/app/services/ai_comparison.py backend/tests/test_poses_router_scoped.py backend/tests/test_day_logs_router_scoped.py backend/tests/test_photos_router_scoped.py
git commit -m "feat: nest photos/poses/day_logs/comparisons routers under /api/clients/{client_id}/*"
```

---

### Task 13: Lightweight migration for `client_id` columns on existing SQLite tables

SQLite's `ALTER TABLE ADD COLUMN` (the codebase's existing lightweight-migration pattern in `app/core/migrations.py`) cannot add a `UNIQUE` constraint to an existing table, and the `Pose`/`DayLog` unique constraints changed shape (single-column → composite). This task adds the plain `client_id` columns via the existing `_PENDING_COLUMNS` mechanism; Task 15 handles backfilling values and doesn't need the constraint to be DB-enforced immediately, since the one-time migration script controls the data directly.

**Files:**
- Modify: `backend/app/core/migrations.py`
- Test: `backend/tests/test_migrations.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_migrations.py
from sqlalchemy import create_engine, inspect, text

from app.core.migrations import run_lightweight_migrations


def test_client_id_column_added_to_pre_existing_tables(tmp_path):
    """Simuliert eine alte DB von vor der Mandantenfähigkeit: legt poses/
    day_logs/photos OHNE client_id an, prüft dass die Migration die Spalte
    nachträgt."""
    db_path = tmp_path / "old.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE poses (id INTEGER PRIMARY KEY, name VARCHAR(100))"))
        conn.execute(text("CREATE TABLE day_logs (id INTEGER PRIMARY KEY, date DATE)"))
        conn.execute(
            text(
                "CREATE TABLE photos (id INTEGER PRIMARY KEY, original_path VARCHAR(1000), "
                "preview_path VARCHAR(1000), thumbnail_path VARCHAR(1000))"
            )
        )

    run_lightweight_migrations(engine)

    inspector = inspect(engine)
    pose_columns = {c["name"] for c in inspector.get_columns("poses")}
    daylog_columns = {c["name"] for c in inspector.get_columns("day_logs")}
    photo_columns = {c["name"] for c in inspector.get_columns("photos")}
    assert "client_id" in pose_columns
    assert "client_id" in daylog_columns
    assert "client_id" in photo_columns
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_migrations.py -v`
Expected: FAIL — `client_id` missing from `poses`/`day_logs` columns (only `photos` already gets columns added by the existing mechanism, and `client_id` isn't in the list yet)

- [ ] **Step 3: Update `_PENDING_COLUMNS` and generalize the migration to check every table**

The current `run_lightweight_migrations` only inspects the `photos` table. Replace the whole file:

```python
"""
Sehr leichtgewichtige Schema-Migration für den POC.

`Base.metadata.create_all()` legt fehlende TABELLEN an, ändert aber nie
Spalten einer bereits existierenden Tabelle. Für neue nullable Spalten an
bestehenden Tabellen reicht hier ein simples "ALTER TABLE ... ADD COLUMN",
statt gleich Alembic aufzusetzen. Für die spätere Cloud-Version sollte das
durch echte Alembic-Migrationen ersetzt werden (siehe README).

Hinweis Mandantenfähigkeit: SQLite kann per ALTER TABLE keine UNIQUE-
Constraints nachrüsten oder ändern (Pose.name/DayLog.date wurden von
global-unique auf unique-pro-Client geändert) - das erledigt stattdessen
das einmalige Migrationsscript (app/core/migrate_to_multitenancy.py), das
diese Tabellen bei Bedarf komplett neu aufbaut. Diese Datei hier trägt nur
die rohe `client_id`-Spalte nach, ohne Constraint.
"""
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

# (Tabelle, Spalte, SQL-Typ) - hier eintragen, wenn ein neues nullable
# Feld zu einem bestehenden Model hinzukommt.
_PENDING_COLUMNS: list[tuple[str, str, str]] = [
    ("photos", "preview_path", "VARCHAR(1000)"),
    ("photos", "thumbnail_path", "VARCHAR(1000)"),
    ("photos", "client_id", "INTEGER"),
    ("poses", "client_id", "INTEGER"),
    ("day_logs", "client_id", "INTEGER"),
]


def run_lightweight_migrations(engine: Engine) -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, column, sql_type in _PENDING_COLUMNS:
            if table not in existing_tables:
                continue  # Frisch angelegte DB - create_all() hat die Spalte schon.
            existing_columns = {col["name"] for col in inspector.get_columns(table)}
            if column in existing_columns:
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_migrations.py -v`
Expected: `1 passed`

- [ ] **Step 5: Run the full backend test suite**

Run: `cd backend && .venv/Scripts/python -m pytest -v`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/migrations.py backend/tests/test_migrations.py
git commit -m "feat: generalize lightweight migration to add client_id columns to all client-scoped tables"
```

---

### Task 14: One-time data migration script (existing single-tenant data → "Mein Profil")

Per the spec's "Migration des bestehenden Datenbestands" section. Runs automatically at startup, detected by "no `User` rows exist yet". This is the one place in the whole plan that touches the real `backend/data/` directory and the real `bodycomp.db` — it must be idempotent (safe to run again with no `User` present) and is the highest-risk step in the whole plan.

**Files:**
- Create: `backend/app/core/migrate_to_multitenancy.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_migrate_to_multitenancy.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_migrate_to_multitenancy.py
from datetime import datetime

from app.core.migrate_to_multitenancy import migrate_to_multitenancy
from app.models.client import Client
from app.models.day_log import DayLog
from app.models.photo import Photo, ProcessingStatus
from app.models.pose import Pose
from app.models.user import User


def _seed_pre_migration_data(db_session):
    """Legt Pose/DayLog/Photo OHNE client_id an - simuliert den Stand vor
    der Mandantenfähigkeit (die Spalte existiert dank Task 13 bereits,
    ist hier aber bewusst NULL)."""
    pose = Pose(name="Front Double Biceps", sort_order=0)
    db_session.add(pose)
    db_session.flush()

    day_log = DayLog(date="2026-01-01", weight_kg=80.0)
    db_session.add(day_log)
    db_session.flush()

    photo = Photo(
        filename="test.jpg",
        original_path="photos_processed/2026-01-01/test.jpg",
        taken_at=datetime(2026, 1, 1, 12, 0, 0),
        status=ProcessingStatus.PROCESSED,
        pose_id=pose.id,
        day_log_id=day_log.id,
    )
    db_session.add(photo)
    db_session.commit()
    return pose, day_log, photo


def test_migration_creates_account_and_client(db_session):
    _seed_pre_migration_data(db_session)

    migrate_to_multitenancy(
        db_session,
        email="basti@example.com",
        password="Grindcore123!",
        display_name="Basti",
    )

    user = db_session.query(User).filter(User.email == "basti@example.com").first()
    assert user is not None
    assert user.account_type.value == "coach"

    client_row = db_session.query(Client).filter(Client.owner_id == user.id).first()
    assert client_row is not None
    assert client_row.name == "Mein Profil"


def test_migration_backfills_client_id_on_existing_rows(db_session):
    pose, day_log, photo = _seed_pre_migration_data(db_session)

    migrate_to_multitenancy(
        db_session,
        email="basti@example.com",
        password="Grindcore123!",
        display_name="Basti",
    )

    client_row = db_session.query(Client).first()
    db_session.refresh(pose)
    db_session.refresh(day_log)
    db_session.refresh(photo)
    assert pose.client_id == client_row.id
    assert day_log.client_id == client_row.id
    assert photo.client_id == client_row.id


def test_migration_is_a_noop_when_a_user_already_exists(db_session):
    _seed_pre_migration_data(db_session)
    migrate_to_multitenancy(
        db_session, email="basti@example.com", password="Grindcore123!", display_name="Basti"
    )
    user_count_after_first_run = db_session.query(User).count()

    migrate_to_multitenancy(
        db_session, email="basti@example.com", password="Grindcore123!", display_name="Basti"
    )
    user_count_after_second_run = db_session.query(User).count()

    assert user_count_after_first_run == user_count_after_second_run == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_migrate_to_multitenancy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.migrate_to_multitenancy'`

- [ ] **Step 3: Write `app/core/migrate_to_multitenancy.py`**

```python
"""
Einmaliges Migrationsscript: verschiebt die bestehenden Single-Tenant-
Daten (Poses/DayLogs/Photos ohne client_id) in einen neuen Client "Mein
Profil", der einem neu angelegten Account gehört - siehe Design-Spec
Abschnitt "Migration des bestehenden Datenbestands".

Wird von main.py's lifespan bei JEDEM Start aufgerufen, ist aber ein
No-Op, sobald mindestens ein User existiert (Erkennungsmerkmal laut
Spec) - so kann es gefahrlos öfter aufgerufen werden, ohne Daten
doppelt zu migrieren.

Bewegt zusätzlich die betroffenen Dateien auf der Platte in die neue
client-gescopte Ordnerstruktur (siehe services/storage_paths.py) und
aktualisiert die in der DB gespeicherten Pfade entsprechend.
"""
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.client import Client
from app.models.day_log import DayLog
from app.models.photo import Photo
from app.models.pose import Pose
from app.models.user import User
from app.services.account import create_account
from app.services.storage_paths import processed_dir_for_client_date


def _move_file_into_client_folder(rel_path: str | None, client_id: int) -> str | None:
    """Verschiebt eine einzelne Datei (original/preview/thumbnail/
    normalized) in den client-gescopten Ordner, behält den restlichen
    Pfad (Datum, Dateiname) bei. Gibt den neuen relativen Pfad zurück,
    oder den unveränderten Wert, wenn die Datei nicht existiert (defensiv
    - eine fehlende Datei blockiert die Migration nicht)."""
    if not rel_path:
        return rel_path

    source = settings.data_dir / rel_path
    if not source.exists():
        return rel_path

    parts = Path(rel_path).parts  # z.B. ("photos_processed", "2026-01-01", "foo.jpg")
    if parts[0] == "photos_processed" and len(parts) >= 3:
        date_str = parts[1]
        filename = Path(*parts[2:])
        dest_dir = processed_dir_for_client_date(client_id, date_str)
    elif parts[0] == "photos_normalized" and len(parts) >= 3:
        pose_id_str = parts[1]
        filename = Path(*parts[2:])
        dest_dir = settings.photos_normalized_dir / str(client_id) / pose_id_str
    elif parts[0] == "photos_incoming" and len(parts) >= 2:
        filename = Path(*parts[1:])
        dest_dir = settings.photos_incoming_dir / str(client_id)
    else:
        return rel_path  # unbekanntes Layout - unverändert lassen

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    shutil.move(str(source), str(dest))
    return dest.relative_to(settings.data_dir).as_posix()


def migrate_to_multitenancy(
    db: Session, *, email: str, password: str, display_name: str
) -> None:
    if db.query(User).count() > 0:
        return  # schon migriert (oder frische Installation ohne Altdaten)

    user = create_account(
        db, email=email, password=password, display_name=display_name
    )
    # create_account legt bereits EINEN Client namens display_name an
    # (siehe services/account.py) - für die Migration bestehender Daten
    # überschreiben wir dessen Namen auf "Mein Profil", statt einen
    # zweiten Client anzulegen.
    client_row = db.query(Client).filter(Client.owner_id == user.id).first()
    client_row.name = "Mein Profil"

    from app.models.user import AccountType

    user.account_type = AccountType.COACH
    db.commit()

    poses = db.query(Pose).filter(Pose.client_id.is_(None)).all()
    for pose in poses:
        pose.client_id = client_row.id

    day_logs = db.query(DayLog).filter(DayLog.client_id.is_(None)).all()
    for day_log in day_logs:
        day_log.client_id = client_row.id

    photos = db.query(Photo).filter(Photo.client_id.is_(None)).all()
    for photo in photos:
        photo.client_id = client_row.id
        photo.original_path = _move_file_into_client_folder(photo.original_path, client_row.id)
        photo.preview_path = _move_file_into_client_folder(photo.preview_path, client_row.id)
        photo.thumbnail_path = _move_file_into_client_folder(photo.thumbnail_path, client_row.id)
        photo.normalized_path = _move_file_into_client_folder(photo.normalized_path, client_row.id)

    db.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_migrate_to_multitenancy.py -v`
Expected: `3 passed`

- [ ] **Step 5: Wire the migration into `main.py`'s lifespan**

```python
from app.core.migrate_to_multitenancy import migrate_to_multitenancy
```

In the `lifespan` function, after `run_lightweight_migrations(engine)` and before the existing `seed_default_poses` call (which Task 8 already removed the global variant of — this whole block replaces it):

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    run_lightweight_migrations(engine)
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

Add `migration_seed_password` to `backend/app/core/config.py`'s `Settings` class, right after `session_secret_key`:

```python
    # Startpasswort für den einmalig migrierten Coach-Account (siehe
    # core/migrate_to_multitenancy.py). NICHT im Repo im Klartext - wird
    # über backend/.env gesetzt (BODYCOMP_MIGRATION_SEED_PASSWORD), nicht
    # committed (siehe .gitignore).
    migration_seed_password: str = "changeme-set-in-dotenv"
```

Add the real value to `backend/.env` (this file is gitignored, never committed):

```
BODYCOMP_MIGRATION_SEED_PASSWORD=Grindcore123!
```

Also add the placeholder to `backend/.env.example` so the pattern is documented for anyone cloning the repo:

```
BODYCOMP_MIGRATION_SEED_PASSWORD=change-me
```

- [ ] **Step 6: Manual verification against the real database**

This step touches real data — back up first.

Run: `cp backend/data/bodycomp.db backend/data/bodycomp.db.pre-migration-backup`

Restart the backend (kill any running uvicorn process on port 8000 first, then):

Run: `cd backend && .venv/Scripts/python -m uvicorn app.main:app --port 8000`

In another terminal, verify:

Run: `curl -s http://127.0.0.1:8000/api/health`
Expected: `{"status":"ok"}`

Run: `curl -s -X POST http://127.0.0.1:8000/api/auth/login -H "Content-Type: application/json" -d '{"email":"basti.auer@outlook.com","password":"Grindcore123!"}' -c /tmp/cookies.txt`
Expected: JSON with `"display_name":"Basti"`, `"account_type":"coach"`

Run: `curl -s http://127.0.0.1:8000/api/clients -b /tmp/cookies.txt`
Expected: one client named `"Mein Profil"`

Run: `curl -s "http://127.0.0.1:8000/api/clients/<id-from-previous-response>/photos" -b /tmp/cookies.txt | python -c "import json,sys; print(len(json.load(sys.stdin)))"`
Expected: `175` (the known photo count from the spec)

If any of these don't match, restore the backup (`cp backend/data/bodycomp.db.pre-migration-backup backend/data/bodycomp.db`) and re-examine the migration function before proceeding — do not continue to Step 7 until this step passes.

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/migrate_to_multitenancy.py backend/app/main.py backend/app/core/config.py backend/.env.example backend/tests/test_migrate_to_multitenancy.py
git commit -m "feat: add one-time migration of existing single-tenant data into 'Mein Profil' client"
```

(`.env` itself is gitignored and never committed — confirm with `git status` that it doesn't appear before this commit)

---

## Part 2 — Frontend

### Task 15: Auth API client + login page

**Files:**
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/pages/Login.tsx`
- Create: `frontend/src/hooks/useCurrentUser.ts`

- [ ] **Step 1: Add auth types and API methods to `client.ts`**

Add near the top of `frontend/src/api/client.ts`, after the existing `DisplaySettings` interface:

```typescript
export type AccountType = "single" | "coach";

export interface CurrentUser {
  id: number;
  email: string;
  display_name: string;
  account_type: AccountType;
}
```

Also add `withCredentials: true` to the axios instance so the httpOnly session cookie is sent automatically on same-origin requests:

```typescript
const client = axios.create({ baseURL: "/api", withCredentials: true });
```

Add a new `auth` section to the `api` object (alongside the existing `poses`/`dayLogs`/`photos`/`settings`/`comparisons` keys):

```typescript
  auth: {
    login: (email: string, password: string) =>
      client.post<CurrentUser>("/auth/login", { email, password }).then((r) => r.data),
    logout: () => client.post("/auth/logout"),
    me: () => client.get<CurrentUser>("/auth/me").then((r) => r.data),
    switchToCoach: () =>
      client.post<CurrentUser>("/auth/switch-to-coach").then((r) => r.data),
  },
```

- [ ] **Step 2: Write `useCurrentUser` hook**

```typescript
// frontend/src/hooks/useCurrentUser.ts
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

/** Lädt den eingeloggten Account. `enabled` steuert React Query's
 * Retry-Verhalten nicht direkt - ein 401 wird hier bewusst NICHT als
 * Query-Error behandelt, sondern über `isError`/`data === undefined`
 * geprüft, damit die aufrufende Seite entscheiden kann, ob sie zum
 * Login redirected. */
export function useCurrentUser() {
  return useQuery({
    queryKey: ["auth", "me"],
    queryFn: api.auth.me,
    retry: false,
  });
}
```

- [ ] **Step 3: Write `Login.tsx`**

```tsx
// frontend/src/pages/Login.tsx
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
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
        {loginMutation.isError && (
          <p className="text-sm text-red-400">E-Mail oder Passwort falsch.</p>
        )}
        <button
          type="submit"
          disabled={loginMutation.isPending}
          className="w-full rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-50"
        >
          {loginMutation.isPending ? "Einloggen…" : "Einloggen"}
        </button>
      </form>
    </div>
  );
}
```

(`/redirect-to-my-client` is a placeholder route wired up properly in Task 16, which adds the actual single-user redirect logic once the client list is fetchable)

- [ ] **Step 4: Manual verification**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/hooks/useCurrentUser.ts frontend/src/pages/Login.tsx
git commit -m "feat: add auth API client, useCurrentUser hook, and login page"
```

---

### Task 16: Route restructuring — `/login`, protected routes, `/clients/:clientId/*`

**Files:**
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/components/RequireAuth.tsx`
- Create: `frontend/src/components/ClientRedirect.tsx`

- [ ] **Step 1: Write `RequireAuth.tsx`**

```tsx
// frontend/src/components/RequireAuth.tsx
import { Navigate, Outlet } from "react-router-dom";
import { useCurrentUser } from "../hooks/useCurrentUser";

/** Schützt alle verschachtelten Routen - ohne gültige Session geht's
 * zurück zu /login. Während des ersten Ladens (noch kein isError/isSuccess)
 * wird nichts gerendert, um kein Flackern der Login-Seite zu erzeugen. */
export default function RequireAuth() {
  const { data: user, isLoading, isError } = useCurrentUser();

  if (isLoading) return null;
  if (isError || !user) return <Navigate to="/login" replace />;

  return <Outlet />;
}
```

- [ ] **Step 2: Write `ClientRedirect.tsx`**

```tsx
// frontend/src/components/ClientRedirect.tsx
import { useQuery } from "@tanstack/react-query";
import { Navigate } from "react-router-dom";
import { api } from "../api/client";
import { useCurrentUser } from "../hooks/useCurrentUser";

/**
 * Root-Route ("/") für eingeloggte Accounts: `single` geht direkt in das
 * eine automatisch angelegte Client-Profil, `coach` sieht das Dashboard
 * (siehe Design-Spec Abschnitt "Kontotyp").
 */
export default function ClientRedirect() {
  const { data: user } = useCurrentUser();
  const clientsQuery = useQuery({ queryKey: ["clients"], queryFn: api.clients.list });

  if (user?.account_type === "coach") {
    return <Navigate to="/dashboard" replace />;
  }

  if (clientsQuery.isLoading) return null;
  const firstClient = clientsQuery.data?.[0];
  if (!firstClient) return null; // sollte nie passieren - jeder Account hat mind. einen Client

  return <Navigate to={`/clients/${firstClient.id}/timeline`} replace />;
}
```

(`api.clients` doesn't exist yet — added in Task 17 alongside the Dashboard; this file references it in anticipation, so Task 17 must land before this compiles cleanly. Both tasks are committed together at the end of Task 17 if you're executing sequentially without intermediate `tsc` checks.)

- [ ] **Step 3: Rewrite `App.tsx`**

```tsx
import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import RequireAuth from "./components/RequireAuth";
import ClientRedirect from "./components/ClientRedirect";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Account from "./pages/Account";
import Timeline from "./pages/Timeline";
import Unprocessed from "./pages/Unprocessed";
import Compare from "./pages/Compare";
import Statistics from "./pages/Statistics";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<RequireAuth />}>
        <Route element={<Layout />}>
          <Route index element={<ClientRedirect />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="account" element={<Account />} />
          <Route path="clients/:clientId/timeline" element={<Timeline />} />
          <Route path="clients/:clientId/unprocessed" element={<Unprocessed />} />
          <Route path="clients/:clientId/compare" element={<Compare />} />
          <Route path="clients/:clientId/statistics" element={<Statistics />} />
          <Route path="clients/:clientId/settings" element={<Settings />} />
        </Route>
      </Route>
    </Routes>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/RequireAuth.tsx frontend/src/components/ClientRedirect.tsx
git commit -m "feat: restructure routes - /login, protected routes, /clients/:clientId/*"
```

(This will not type-check cleanly until Task 17 adds `api.clients` and the pages accept a `clientId` param — that's expected and resolved by the end of Task 18.)

---

### Task 17: Dashboard page + `api.clients`

**Files:**
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: Add `Client` type and `api.clients` to `client.ts`**

Add to `frontend/src/types/index.ts`:

```typescript
export interface Client {
  id: number;
  name: string;
  height_cm: number | null;
  age: number | null;
  gender: string | null;
  start_date: string | null;
  created_at: string;
}
```

Add to `frontend/src/api/client.ts` (import `Client` alongside the existing type imports at the top, then add this section to the `api` object):

```typescript
  clients: {
    list: () => client.get<Client[]>("/clients").then((r) => r.data),
    get: (clientId: number) => client.get<Client>(`/clients/${clientId}`).then((r) => r.data),
    create: (payload: {
      name: string;
      height_cm?: number | null;
      age?: number | null;
      gender?: string | null;
      start_date?: string | null;
    }) => client.post<Client>("/clients", payload).then((r) => r.data),
    update: (clientId: number, payload: Partial<Omit<Client, "id" | "created_at">>) =>
      client.patch<Client>(`/clients/${clientId}`, payload).then((r) => r.data),
  },
```

- [ ] **Step 2: Write `Dashboard.tsx`**

```tsx
// frontend/src/pages/Dashboard.tsx
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";

export default function Dashboard() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [heightCm, setHeightCm] = useState("");
  const [age, setAge] = useState("");
  const [gender, setGender] = useState("");
  const [startDate, setStartDate] = useState("");

  const clientsQuery = useQuery({ queryKey: ["clients"], queryFn: api.clients.list });

  const createMutation = useMutation({
    mutationFn: () =>
      api.clients.create({
        name,
        height_cm: heightCm.trim() === "" ? null : Number(heightCm),
        age: age.trim() === "" ? null : Number(age),
        gender: gender.trim() === "" ? null : gender,
        start_date: startDate.trim() === "" ? null : startDate,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clients"] });
      setShowForm(false);
      setName("");
      setHeightCm("");
      setAge("");
      setGender("");
      setStartDate("");
    },
  });

  const clients = clientsQuery.data ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-white">Meine Kunden</h1>
        <button
          onClick={() => setShowForm((s) => !s)}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90"
        >
          Neuen Kunden anlegen
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim()) createMutation.mutate();
          }}
          className="grid grid-cols-1 gap-3 rounded-xl border border-white/5 bg-surface p-4 sm:grid-cols-2"
        >
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Name
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Körpergröße (cm)
            <input
              type="number"
              value={heightCm}
              onChange={(e) => setHeightCm(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Alter
            <input
              type="number"
              value={age}
              onChange={(e) => setAge(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Geschlecht
            <input
              value={gender}
              onChange={(e) => setGender(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Startdatum
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <div className="flex items-end">
            <button
              type="submit"
              disabled={!name.trim() || createMutation.isPending}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-40"
            >
              {createMutation.isPending ? "Anlegen…" : "Anlegen"}
            </button>
          </div>
        </form>
      )}

      {clientsQuery.isLoading && <p className="text-slate-500">Lade…</p>}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {clients.map((c) => (
          <Link
            key={c.id}
            to={`/clients/${c.id}/timeline`}
            className="rounded-xl border border-white/5 bg-surface p-4 transition-colors hover:border-accent/40"
          >
            <p className="text-base font-semibold text-white">{c.name}</p>
            <p className="mt-1 text-xs text-slate-500">
              {[c.age ? `${c.age} Jahre` : null, c.height_cm ? `${c.height_cm} cm` : null]
                .filter(Boolean)
                .join(" · ") || "Keine Metriken hinterlegt"}
            </p>
          </Link>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors related to `Dashboard.tsx`, `client.ts`, `types/index.ts`. `ClientRedirect.tsx` (Task 16) should now also compile cleanly since `api.clients.list` exists.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/types/index.ts frontend/src/pages/Dashboard.tsx
git commit -m "feat: add Dashboard page with client list and create-client form"
```

---

### Task 18: Account page (Gemini key + display settings + account-type toggle)

Moves the account-scoped Settings pieces (currently mixed into `Settings.tsx` with pose config) into their own page. Pose configuration stays on the existing `Settings.tsx` (now client-scoped).

**Files:**
- Read first: `frontend/src/pages/Settings.tsx` (to see exactly what's Gemini-key/display-settings vs. pose-config before splitting)
- Create: `frontend/src/pages/Account.tsx`
- Modify: `frontend/src/pages/Settings.tsx`

- [ ] **Step 1: Read the current `Settings.tsx` in full**

Run: `cat frontend/src/pages/Settings.tsx`

Identify the JSX/state blocks for: (a) Gemini key display/edit, (b) display settings (timeline columns/weeks-per-page), (c) pose list CRUD. (a) and (b) move to the new `Account.tsx`; (c) stays in `Settings.tsx`.

- [ ] **Step 2: Write `Account.tsx`**

Move the Gemini-key and display-settings JSX/state/mutations verbatim out of `Settings.tsx` into this new file, keeping their existing `api.settings.*` calls unchanged (those endpoints didn't change their request/response shape in Task 10 — only their auth scoping, which is transparent to the frontend since the session cookie is sent automatically). Add the account-type toggle at the top:

```tsx
// frontend/src/pages/Account.tsx
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useCurrentUser } from "../hooks/useCurrentUser";

export default function Account() {
  const queryClient = useQueryClient();
  const { data: user } = useCurrentUser();

  const switchToCoachMutation = useMutation({
    mutationFn: api.auth.switchToCoach,
    onSuccess: (updatedUser) => {
      queryClient.setQueryData(["auth", "me"], updatedUser);
    },
  });

  return (
    <div className="max-w-xl space-y-6">
      <h1 className="text-xl font-semibold text-white">Account</h1>

      {user?.account_type === "single" && (
        <div className="rounded-xl border border-white/5 bg-surface p-4">
          <h2 className="mb-1 text-lg font-semibold text-white">Kontotyp</h2>
          <p className="mb-4 text-sm text-slate-400">
            Du trackst aktuell nur dich selbst. Wenn du auch andere Kunden betreust, kannst du
            hier ein Dashboard mit mehreren Kundenprofilen freischalten.
          </p>
          <button
            onClick={() => switchToCoachMutation.mutate()}
            disabled={switchToCoachMutation.isPending}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-50"
          >
            {switchToCoachMutation.isPending ? "Wird umgestellt…" : "Ich betreue auch andere Kunden"}
          </button>
        </div>
      )}

      {/* Gemini-Key- und Anzeige-Einstellungen-JSX aus der bisherigen
          Settings.tsx werden hier unverändert eingefügt (siehe Schritt 1). */}
    </div>
  );
}
```

- [ ] **Step 3: Remove the moved sections from `Settings.tsx`**

Delete the Gemini-key and display-settings JSX/state/mutations from `Settings.tsx`, leaving only the pose-config list/create/rename/delete UI and its `api.poses.*` calls (which Task 19 updates to be client-scoped).

- [ ] **Step 4: Add the `/account` nav entry (done in Task 20 alongside the rest of `Layout.tsx`'s nav) — no action here.**

- [ ] **Step 5: Verify type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors (some may remain from `Settings.tsx`'s pose calls until Task 19 lands — that's expected).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Account.tsx frontend/src/pages/Settings.tsx
git commit -m "feat: split Account page (Gemini key, display settings, account-type toggle) out of Settings"
```

---

### Task 19: Client-scope all existing pages' API calls

Every existing page (`Timeline`, `Unprocessed`, `Compare`, `Statistics`, `Settings`) currently calls e.g. `api.photos.list()` with no client context. They now read `clientId` from the URL (`useParams`) and every `api.*` call for photos/poses/day-logs/comparisons needs that `clientId` threaded through — both in the page components and in `client.ts`'s method signatures.

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/Timeline.tsx`
- Modify: `frontend/src/pages/Unprocessed.tsx`
- Modify: `frontend/src/pages/Compare.tsx`
- Modify: `frontend/src/pages/Statistics.tsx`
- Modify: `frontend/src/pages/Settings.tsx`

- [ ] **Step 1: Update every client-scoped method in `client.ts`**

Every method under `poses`, `dayLogs`, `photos`, `comparisons` gets a `clientId: number` as its first parameter, and the URL gains the `/clients/${clientId}` prefix. Apply this transform to each:

```typescript
  poses: {
    list: (clientId: number) => client.get<Pose[]>(`/clients/${clientId}/poses`).then((r) => r.data),
    create: (clientId: number, name: string) =>
      client.post<Pose>(`/clients/${clientId}/poses`, { name }).then((r) => r.data),
    update: (clientId: number, id: number, payload: Partial<Pick<Pose, "name" | "sort_order">>) =>
      client.patch<Pose>(`/clients/${clientId}/poses/${id}`, payload).then((r) => r.data),
    remove: (clientId: number, id: number) => client.delete(`/clients/${clientId}/poses/${id}`),
  },
  dayLogs: {
    list: (clientId: number) => client.get<DayLog[]>(`/clients/${clientId}/day-logs`).then((r) => r.data),
    upsert: (clientId: number, payload: { date: string; weight_kg?: number | null; notes?: string | null }) =>
      client.put<DayLog>(`/clients/${clientId}/day-logs`, payload).then((r) => r.data),
  },
  photos: {
    sync: (clientId: number) => client.post<Photo[]>(`/clients/${clientId}/photos/sync`).then((r) => r.data),
    unprocessed: (clientId: number) =>
      client.get<UnprocessedPhoto[]>(`/clients/${clientId}/photos/unprocessed`).then((r) => r.data),
    list: (clientId: number, params?: { pose_id?: number; status?: string }) =>
      client.get<Photo[]>(`/clients/${clientId}/photos`, { params }).then((r) => r.data),
    assign: (clientId: number, id: number, payload: { pose_id: number; weight_kg?: number | null }) =>
      client.post<Photo>(`/clients/${clientId}/photos/${id}/assign`, payload).then((r) => r.data),
    assignBulk: (clientId: number, items: { photo_id: number; pose_id: number; weight_kg?: number | null }[]) =>
      client.post<Photo[]>(`/clients/${clientId}/photos/assign-bulk`, { items }).then((r) => r.data),
    remove: (clientId: number, id: number) => client.delete(`/clients/${clientId}/photos/${id}`),
    removeByDate: (clientId: number, date: string) =>
      client.delete<{ deleted: number }>(`/clients/${clientId}/photos/by-date/${date}`).then((r) => r.data),
    changePose: (clientId: number, id: number, poseId: number) =>
      client.patch<Photo>(`/clients/${clientId}/photos/${id}/pose`, { pose_id: poseId }).then((r) => r.data),
    upload: (clientId: number, files: File[]) => {
      const form = new FormData();
      for (const file of files) form.append("files", file);
      return client
        .post<UnprocessedPhoto[]>(`/clients/${clientId}/photos/upload`, form, {
          headers: { "Content-Type": "multipart/form-data" },
        })
        .then((r) => r.data);
    },
  },
```

```typescript
  comparisons: {
    get: (clientId: number, params: { pose_id: number; date_x: string; date_y: string }) =>
      client
        .get<{ photo_x: Photo; photo_y: Photo }>(`/clients/${clientId}/comparisons`, { params })
        .then((r) => r.data),
    aiAnalysis: (clientId: number, params: { pose_id: number; date_x: string; date_y: string }) =>
      client
        .get<{ analysis: string }>(`/clients/${clientId}/comparisons/ai-analysis`, { params })
        .then((r) => r.data),
    aiAnalysisAll: (clientId: number, params: { date_x: string; date_y: string }) =>
      client
        .get<{ analysis: string }>(`/clients/${clientId}/comparisons/ai-analysis-all`, { params })
        .then((r) => r.data),
  },
```

(`settings` stays unchanged — it's account-scoped, not client-scoped, per Task 10/18)

- [ ] **Step 2: Update each page to read `clientId` from the route and pass it through**

For each of `Timeline.tsx`, `Unprocessed.tsx`, `Compare.tsx`, `Statistics.tsx`, `Settings.tsx`:

1. Add `import { useParams } from "react-router-dom";` if not already present
2. Add near the top of the component: `const { clientId } = useParams<{ clientId: string }>(); const clientIdNum = Number(clientId);`
3. Every `api.poses.*(...)`, `api.dayLogs.*(...)`, `api.photos.*(...)`, `api.comparisons.*(...)` call gets `clientIdNum` inserted as the new first argument
4. Every React Query `queryKey` array that identifies these queries gets `clientIdNum` inserted as an element (e.g. `["photos", "all"]` → `["photos", "all", clientIdNum]`) so React Query correctly refetches when the user switches clients via the URL instead of serving stale cached data from a different client

This is a mechanical, per-file transform — there is no shared logic to extract since each page's existing query/mutation calls already differ in shape. Apply steps 1–4 to each file individually, re-running `tsc` after each file to catch missed call sites (TypeScript will flag every `api.photos.list()` call now missing its required `clientId` argument as a compile error, which is a strong forcing function to find every call site) — do not do this file by file with a build check only at the end, since TypeScript's error output for one file can be misleading when four other files are still broken.

- [ ] **Step 3: Verify type-check after all five files are updated**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/pages/Timeline.tsx frontend/src/pages/Unprocessed.tsx frontend/src/pages/Compare.tsx frontend/src/pages/Statistics.tsx frontend/src/pages/Settings.tsx
git commit -m "feat: thread clientId from URL through every client-scoped API call and query key"
```

---

### Task 20: Navigation — client name, dashboard link, account link, logout, single/coach visibility

**Files:**
- Modify: `frontend/src/components/Layout.tsx`

- [ ] **Step 1: Rewrite `Layout.tsx`**

```tsx
import { NavLink, Outlet, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useCurrentUser } from "../hooks/useCurrentUser";

export default function Layout() {
  const { clientId } = useParams<{ clientId: string }>();
  const { data: user } = useCurrentUser();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const clientQuery = useQuery({
    queryKey: ["clients", clientId],
    queryFn: () => api.clients.get(Number(clientId)),
    enabled: !!clientId,
  });

  const logoutMutation = useMutation({
    mutationFn: api.auth.logout,
    onSuccess: () => {
      queryClient.clear();
      navigate("/login");
    },
  });

  const navItems = clientId
    ? [
        { to: `/clients/${clientId}/timeline`, label: "Timeline", end: true },
        { to: `/clients/${clientId}/unprocessed`, label: "Import" },
        { to: `/clients/${clientId}/compare`, label: "Compare" },
        { to: `/clients/${clientId}/statistics`, label: "Statistik" },
        { to: `/clients/${clientId}/settings`, label: "Settings" },
      ]
    : [];

  return (
    <div className="min-h-screen bg-background text-slate-100">
      <header className="sticky top-0 z-20 border-b border-white/5 bg-background/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold tracking-wide text-white">
              BodyComp <span className="text-accent">Tracker</span>
            </span>
            {user?.account_type === "coach" && clientQuery.data && (
              <>
                <span className="text-slate-600">·</span>
                <NavLink to="/dashboard" className="text-xs text-slate-400 hover:text-white">
                  ← Dashboard
                </NavLink>
                <span className="text-sm text-slate-300">{clientQuery.data.name}</span>
              </>
            )}
          </div>
          <div className="flex items-center gap-3">
            <nav className="flex gap-1 rounded-full bg-surface p-1">
              {navItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    `rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
                      isActive ? "bg-accent text-slate-900" : "text-slate-400 hover:text-white"
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
            <NavLink
              to="/account"
              className="text-xs text-slate-400 hover:text-white"
            >
              Account
            </NavLink>
            <button
              onClick={() => logoutMutation.mutate()}
              className="text-xs text-slate-400 hover:text-white"
            >
              Logout
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
        <Outlet />
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Verify type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Layout.tsx
git commit -m "feat: nav bar shows active client name (coach only), dashboard link, account link, logout"
```

---

## Final verification (manual, whole app)

After all 20 tasks are complete and committed on `dev`:

- [ ] Run the full backend test suite: `cd backend && .venv/Scripts/python -m pytest -v` — all green.
- [ ] Run `cd frontend && npx tsc --noEmit` — no errors.
- [ ] Start both servers (backend on :8000, frontend on :5173), log in as `basti.auer@outlook.com`, confirm the Dashboard shows "Mein Profil" with all 175 photos intact when opened.
- [ ] Create a second test client from the Dashboard, confirm it gets its own 7 default poses and an empty Timeline.
- [ ] Confirm switching between the two clients via the Dashboard never shows the other client's photos (check Network tab: every request URL includes the correct `client_id`).
- [ ] Log out, confirm redirect to `/login` and that `/dashboard` is unreachable without logging back in.
