# Account Profile Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a logged-in user see their email + account age, change their password (if they have one), and change their email address via a confirm-by-link flow (if not a Google-only account).

**Architecture:** Two new `EmailToken`-based backend endpoints (`change-password`, `change-email` + its public `confirm-email-change` confirmation endpoint) reusing the existing password-hash/email-token/rate-limit infrastructure, plus `UserOut` schema additions (`created_at`, `has_google_account`). Frontend adds a `ProfileSection` to `Account.tsx` and a new public `ConfirmEmailChange` page mirroring the existing `VerifyEmail` page.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic v2, Alembic, itsdangerous (email tokens), bcrypt, React, TanStack Query, react-router-dom.

---

### Task 1: `new_email` column on EmailToken + `CHANGE_EMAIL` purpose

**Files:**
- Modify: `backend/app/models/email_token.py`
- Modify: `backend/app/core/migrations.py`
- Create: `backend/alembic/versions/0004_email_token_new_email.py`
- Test: `backend/tests/test_email_token_model.py`

- [ ] **Step 1: Write the failing test**

Check first whether `backend/tests/test_email_token_model.py` already exists:

```bash
ls backend/tests/test_email_token_model.py 2>&1
```

If it doesn't exist, create it with this content. If it does exist, add this test function to it (keep existing tests untouched):

```python
from datetime import datetime, timedelta, timezone

from app.models.email_token import EmailToken, EmailTokenPurpose
from app.models.user import User
from app.services.auth import hash_password


def test_email_token_supports_change_email_purpose_with_new_email(db_session):
    user = User(
        email="old@example.com",
        password_hash=hash_password("Grindcore123!"),
        display_name="Basti",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    token = EmailToken(
        user_id=user.id,
        token_hash="deadbeef",
        purpose=EmailTokenPurpose.CHANGE_EMAIL,
        new_email="new@example.com",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db_session.add(token)
    db_session.commit()
    db_session.refresh(token)

    assert token.purpose == EmailTokenPurpose.CHANGE_EMAIL
    assert token.new_email == "new@example.com"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_email_token_model.py -v`
Expected: FAIL - either `AttributeError: CHANGE_EMAIL` (enum member doesn't exist yet) or a SQL error about the `new_email` column not existing.

- [ ] **Step 3: Add the `CHANGE_EMAIL` purpose and `new_email` column**

In `backend/app/models/email_token.py`, update the purpose enum and add the column:

```python
class EmailTokenPurpose(str, enum.Enum):
    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"
    CHANGE_EMAIL = "change_email"
```

Add this column to the `EmailToken` class, right after `token_hash`:

```python
    # Nur für purpose=CHANGE_EMAIL gesetzt - trägt die angefragte neue
    # Adresse, bis der Bestätigungslink geklickt wird (siehe
    # routers/auth.py change_email/confirm_email_change). Für alle
    # anderen Purposes bleibt das Feld NULL.
    new_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
```

- [ ] **Step 4: Register the column in the lightweight SQLite migration**

In `backend/app/core/migrations.py`, add this line to `_PENDING_COLUMNS` (at the end, before the closing `]`):

```python
    ("email_tokens", "new_email", "VARCHAR(255)"),
```

- [ ] **Step 5: Create the real Alembic migration**

Check the current head revision first:

```bash
cd backend && .venv/Scripts/python -m alembic heads
```

Create `backend/alembic/versions/0004_email_token_new_email.py` (replace `down_revision` with whatever the `alembic heads` output showed if it isn't `0003_onboarding_field`):

```python
"""new_email on email_tokens

Revision ID: 0004_email_token_new_email
Revises: 0003_onboarding_field
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_email_token_new_email"
down_revision = "0003_onboarding_field"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("email_tokens", sa.Column("new_email", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("email_tokens", "new_email")
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_email_token_model.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/email_token.py backend/app/core/migrations.py backend/alembic/versions/0004_email_token_new_email.py backend/tests/test_email_token_model.py
git commit -m "feat: add CHANGE_EMAIL purpose and new_email column to EmailToken"
```

---

### Task 2: `UserOut.created_at` and `has_google_account`

**Files:**
- Modify: `backend/app/schemas/auth.py`
- Test: `backend/tests/test_auth_router.py`

- [ ] **Step 1: Write the failing test**

Add this test function to `backend/tests/test_auth_router.py` (append near `test_me_returns_current_user_after_login`):

```python
def test_me_includes_created_at_and_has_google_account(client, db_session):
    _make_user(db_session)
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    body = response.json()
    assert body["created_at"] is not None
    assert body["has_google_account"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_auth_router.py::test_me_includes_created_at_and_has_google_account -v`
Expected: FAIL with a `KeyError` on `body["created_at"]` (field not in the response yet).

- [ ] **Step 3: Add the fields to UserOut**

In `backend/app/schemas/auth.py`, the current `UserOut` looks like:

```python
class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    account_type: AccountType
    # Nicht Teil der API-Antwort (exclude=True) - nur intern gelesen, damit
    # `has_password` unten berechnet werden kann. Das Frontend braucht das,
    # um z.B. bei der Konto-Löschung das Passwortfeld nur bei Accounts mit
    # Passwort anzuzeigen (Google-only-Accounts haben keins).
    password_hash: str | None = Field(default=None, exclude=True)
    subscription_status: str | None
    subscription_tier: str | None
    trial_ends_at: datetime | None
    free_checkins_used: int
    onboarding_completed_at: datetime | None

    class Config:
        from_attributes = True

    @computed_field
    @property
    def has_password(self) -> bool:
        return self.password_hash is not None
```

Replace it with:

```python
class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    account_type: AccountType
    created_at: datetime
    # Nicht Teil der API-Antwort (exclude=True) - nur intern gelesen, damit
    # `has_password` unten berechnet werden kann. Das Frontend braucht das,
    # um z.B. bei der Konto-Löschung das Passwortfeld nur bei Accounts mit
    # Passwort anzuzeigen (Google-only-Accounts haben keins).
    password_hash: str | None = Field(default=None, exclude=True)
    # Analog zu password_hash - roh nicht Teil der Antwort, nur zur
    # Berechnung von has_google_account. Steuert im Frontend, ob der
    # E-Mail-Änderungsbereich angezeigt wird (Google-Accounts loggen sich
    # über Google ein, eine eigene E-Mail-Änderung ergibt da keinen Sinn).
    google_id: str | None = Field(default=None, exclude=True)
    subscription_status: str | None
    subscription_tier: str | None
    trial_ends_at: datetime | None
    free_checkins_used: int
    onboarding_completed_at: datetime | None

    class Config:
        from_attributes = True

    @computed_field
    @property
    def has_password(self) -> bool:
        return self.password_hash is not None

    @computed_field
    @property
    def has_google_account(self) -> bool:
        return self.google_id is not None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_auth_router.py::test_me_includes_created_at_and_has_google_account -v`
Expected: PASS

- [ ] **Step 5: Run the full auth router test suite to check for regressions**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_auth_router.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/auth.py backend/tests/test_auth_router.py
git commit -m "feat: expose created_at and has_google_account on UserOut"
```

---

### Task 3: `POST /api/auth/change-password` endpoint

**Files:**
- Modify: `backend/app/routers/auth.py`
- Test: `backend/tests/test_auth_router.py`

- [ ] **Step 1: Write the failing tests**

Add these test functions to `backend/tests/test_auth_router.py`:

```python
def test_change_password_requires_login(client, db_session):
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": "x", "new_password": "NewPass123!"},
    )
    assert response.status_code == 401


def test_change_password_rejects_wrong_current_password(client, db_session):
    _make_user(db_session)
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": "wrong", "new_password": "NewPass123!"},
    )
    assert response.status_code == 401


def test_change_password_rejects_too_short_new_password(client, db_session):
    _make_user(db_session)
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": "Grindcore123!", "new_password": "short"},
    )
    assert response.status_code == 422


def test_change_password_succeeds_and_new_password_works_on_next_login(client, db_session):
    _make_user(db_session)
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": "Grindcore123!", "new_password": "NewPass123!"},
    )
    assert response.status_code == 204

    client.post("/api/auth/logout")
    login_response = client.post(
        "/api/auth/login", json={"email": "basti@example.com", "password": "NewPass123!"}
    )
    assert login_response.status_code == 200


def test_change_password_rejects_google_only_account(client, db_session):
    user = User(
        email="google@example.com",
        password_hash=None,
        google_id="google-sub-123",
        display_name="Google User",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.commit()

    # Google-only-Accounts können sich nicht per Passwort einloggen - die
    # Session wird hier direkt über den Login-Endpunkt simuliert, indem wir
    # stattdessen die Session-Cookie-Mechanik nutzen: einfacher ist es, den
    # bestehenden Login-mit-Passwort-Weg für Google-Accounts NICHT zu
    # testen (den gibt's nicht) und stattdessen direkt zu prüfen, dass der
    # Endpunkt bei fehlendem Passwort-Hash ablehnt, sobald ein Cookie da
    # ist. Dazu erzeugen wir die Session wie login() es tun würde.
    from app.services.auth import create_session_token, SESSION_COOKIE_NAME
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    response = client.post(
        "/api/auth/change-password",
        json={"current_password": "anything", "new_password": "NewPass123!"},
    )
    assert response.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_auth_router.py -k change_password -v`
Expected: FAIL with 404 (endpoint doesn't exist yet).

- [ ] **Step 3: Add the schema and endpoint**

In `backend/app/schemas/signup.py`, add this class at the end of the file:

```python
class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)
```

In `backend/app/routers/auth.py`, add the import (alongside the existing `SignupRequest, ResetPasswordRequest` import):

```python
from app.schemas.signup import ChangePasswordRequest, ForgotPasswordRequest, ResetPasswordRequest, SignupRequest
```

Add a new rate limiter near the other rate limiter definitions (`signup_rate_limit = ...` etc, around line 51-53):

```python
change_password_rate_limit = RateLimiter(max_requests=5, window_seconds=3600)
```

Add the import for `verify_password` and `hash_password` if not already imported - check the current import block from `app.services.auth`:

```bash
grep -n "from app.services.auth import" backend/app/routers/auth.py
```

Add `hash_password` and `verify_password` to that import list if missing.

Add the new endpoint right after the `/me` endpoint (after `def me(...)` block, before `/switch-to-coach`):

```python
@router.post("/change-password", status_code=204)
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(change_password_rate_limit),
):
    if current_user.password_hash is None:
        # Google-only-Account - hat kein Passwort zum Ändern. Das Frontend
        # blendet diesen Bereich bereits aus (has_password=false), das
        # hier ist nur die serverseitige Absicherung.
        raise HTTPException(400, "This account has no password set")
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(401, "Current password is incorrect")
    current_user.password_hash = hash_password(payload.new_password)
    db.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_auth_router.py -k change_password -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/signup.py backend/app/routers/auth.py backend/tests/test_auth_router.py
git commit -m "feat: add POST /api/auth/change-password endpoint"
```

---

### Task 4: `POST /api/auth/change-email` + `GET /api/auth/confirm-email-change` endpoints

**Files:**
- Modify: `backend/app/routers/auth.py`
- Modify: `backend/app/services/email.py`
- Test: `backend/tests/test_auth_router.py`

- [ ] **Step 1: Write the failing tests**

Add these test functions to `backend/tests/test_auth_router.py`:

```python
def test_change_email_requires_login(client, db_session):
    response = client.post(
        "/api/auth/change-email",
        json={"new_email": "new@example.com", "current_password": "x"},
    )
    assert response.status_code == 401


def test_change_email_rejects_wrong_password(client, db_session, monkeypatch):
    monkeypatch.setattr("app.routers.auth.send_email_change_confirmation", lambda **kwargs: None)
    _make_user(db_session)
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})
    response = client.post(
        "/api/auth/change-email",
        json={"new_email": "new@example.com", "current_password": "wrong"},
    )
    assert response.status_code == 401


def test_change_email_rejects_already_taken_address(client, db_session, monkeypatch):
    monkeypatch.setattr("app.routers.auth.send_email_change_confirmation", lambda **kwargs: None)
    _make_user(db_session)
    _make_user(db_session, email="taken@example.com", password="Other123!")
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})
    response = client.post(
        "/api/auth/change-email",
        json={"new_email": "taken@example.com", "current_password": "Grindcore123!"},
    )
    assert response.status_code == 409


def test_change_email_does_not_change_email_immediately(client, db_session, monkeypatch):
    monkeypatch.setattr("app.routers.auth.send_email_change_confirmation", lambda **kwargs: None)
    _make_user(db_session)
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})
    response = client.post(
        "/api/auth/change-email",
        json={"new_email": "new@example.com", "current_password": "Grindcore123!"},
    )
    assert response.status_code == 204

    me = client.get("/api/auth/me").json()
    assert me["email"] == "basti@example.com"  # noch unverändert


def test_confirm_email_change_updates_email_with_valid_token(client, db_session, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.routers.auth.send_email_change_confirmation",
        lambda **kwargs: sent.append(kwargs),
    )
    _make_user(db_session)
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})
    client.post(
        "/api/auth/change-email",
        json={"new_email": "new@example.com", "current_password": "Grindcore123!"},
    )
    assert len(sent) == 1
    confirm_url = sent[0]["confirm_url"]
    token = confirm_url.split("token=")[1]

    response = client.get(f"/api/auth/confirm-email-change?token={token}")
    assert response.status_code == 200
    assert response.json()["new_email"] == "new@example.com"

    me = client.get("/api/auth/me").json()
    assert me["email"] == "new@example.com"


def test_confirm_email_change_rejects_invalid_token(client, db_session):
    response = client.get("/api/auth/confirm-email-change?token=garbage")
    assert response.status_code == 400


def test_confirm_email_change_rejects_already_used_token(client, db_session, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.routers.auth.send_email_change_confirmation",
        lambda **kwargs: sent.append(kwargs),
    )
    _make_user(db_session)
    client.post("/api/auth/login", json={"email": "basti@example.com", "password": "Grindcore123!"})
    client.post(
        "/api/auth/change-email",
        json={"new_email": "new@example.com", "current_password": "Grindcore123!"},
    )
    token = sent[0]["confirm_url"].split("token=")[1]

    first = client.get(f"/api/auth/confirm-email-change?token={token}")
    assert first.status_code == 200
    second = client.get(f"/api/auth/confirm-email-change?token={token}")
    assert second.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_auth_router.py -k "change_email or confirm_email" -v`
Expected: FAIL (endpoints don't exist yet / `send_email_change_confirmation` doesn't exist).

- [ ] **Step 3: Add the email service function**

In `backend/app/services/email.py`, add this function right after `send_verification_email`:

```python
def send_email_change_confirmation(*, to: str, confirm_url: str) -> None:
    html = _base_email_html(
        "Confirm your new email address",
        f"""
        <p>Click the link below to confirm this as your new BodyComp Tracker
        login email:</p>
        <p><a href="{confirm_url}">{confirm_url}</a></p>
        <p style="color: #64748b; font-size: 13px;">This link is valid for 24 hours.
        If you didn't request this change, you can safely ignore this email -
        your login email stays unchanged.</p>
        """,
    )
    resend.Emails.send({
        "from": settings.email_from_address,
        "to": [to],
        "subject": "Confirm your new email address - BodyComp Tracker",
        "html": html,
    })
```

- [ ] **Step 4: Add the schema**

In `backend/app/schemas/signup.py`, add this class at the end:

```python
class ChangeEmailRequest(BaseModel):
    new_email: EmailStr
    current_password: str
```

- [ ] **Step 5: Add the endpoints**

In `backend/app/routers/auth.py`, update the import from `app.schemas.signup`:

```python
from app.schemas.signup import (
    ChangeEmailRequest,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    SignupRequest,
)
```

Update the import from `app.services.email` to include the new function - check current import:

```bash
grep -n "from app.services.email import" backend/app/routers/auth.py
```

Add `send_email_change_confirmation` to that import list.

Add a new rate limiter near `change_password_rate_limit`:

```python
change_email_rate_limit = RateLimiter(max_requests=5, window_seconds=3600)
```

Add both new endpoints right after the `change_password` endpoint from Task 3:

```python
@router.post("/change-email", status_code=204)
def change_email(
    payload: ChangeEmailRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(change_email_rate_limit),
):
    if current_user.password_hash is None:
        # Google-only-Account - Frontend blendet diesen Bereich bereits
        # aus, das hier ist nur die serverseitige Absicherung.
        raise HTTPException(400, "This account has no password set")
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(401, "Current password is incorrect")

    existing = (
        db.query(User)
        .filter(User.email == payload.new_email, User.id != current_user.id)
        .first()
    )
    if existing is not None:
        raise HTTPException(409, "This email address is already in use")

    # Vorherige offene CHANGE_EMAIL-Tokens dieses Nutzers invalidieren -
    # nur der neueste angeforderte Link soll gültig sein.
    db.query(EmailToken).filter(
        EmailToken.user_id == current_user.id,
        EmailToken.purpose == EmailTokenPurpose.CHANGE_EMAIL,
        EmailToken.used_at.is_(None),
    ).update({"used_at": datetime.now(timezone.utc)})

    raw_token = create_email_token(user_id=current_user.id, purpose=EmailTokenPurpose.CHANGE_EMAIL.value)
    db.add(EmailToken(
        user_id=current_user.id,
        token_hash=hash_email_token(raw_token),
        purpose=EmailTokenPurpose.CHANGE_EMAIL,
        new_email=payload.new_email,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    ))
    db.commit()

    confirm_url = f"{settings.frontend_base_url.rstrip('/')}/confirm-email-change?token={raw_token}"
    send_email_change_confirmation(to=payload.new_email, confirm_url=confirm_url)


@router.get("/confirm-email-change")
def confirm_email_change(token: str, db: Session = Depends(get_db)):
    payload = verify_email_token_signature(token, max_age_seconds=60 * 60 * 24)
    if payload is None or payload.get("purpose") != EmailTokenPurpose.CHANGE_EMAIL.value:
        raise HTTPException(400, "Link is invalid or expired")

    token_row = (
        db.query(EmailToken)
        .filter(
            EmailToken.user_id == payload["user_id"],
            EmailToken.token_hash == hash_email_token(token),
            EmailToken.purpose == EmailTokenPurpose.CHANGE_EMAIL,
            EmailToken.used_at.is_(None),
        )
        .first()
    )
    if token_row is None:
        raise HTTPException(400, "Link is invalid, expired, or already used")

    user = db.get(User, payload["user_id"])
    user.email = token_row.new_email
    token_row.used_at = datetime.now(timezone.utc)
    db.commit()

    return {"changed": True, "new_email": user.email}
```

Verify `timedelta` and `EmailToken`/`EmailTokenPurpose` are already imported at the top of `auth.py` - check:

```bash
grep -n "^from datetime import\|^from app.models.email_token import" backend/app/routers/auth.py
```

If `timedelta` isn't in the `datetime` import line, add it.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_auth_router.py -k "change_email or confirm_email" -v`
Expected: all PASS

- [ ] **Step 7: Run the full backend test suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all PASS except the pre-existing unrelated failure `test_gemini_key_is_scoped_per_account` (known flaky/unrelated - confirm it's the only failure, if any OTHER test fails investigate before proceeding).

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/email.py backend/app/schemas/signup.py backend/app/routers/auth.py backend/tests/test_auth_router.py
git commit -m "feat: add change-email request/confirm endpoints"
```

---

### Task 5: Frontend API client + types

**Files:**
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Update the `CurrentUser` interface**

In `frontend/src/api/client.ts`, replace the `CurrentUser` interface:

```typescript
export interface CurrentUser {
  id: number;
  email: string;
  display_name: string;
  account_type: AccountType;
  created_at: string;
  // false bei Google-only-Accounts (kein eigenes Passwort gesetzt) -
  // steuert z.B. ob bei der Konto-Löschung ein Passwortfeld angezeigt wird.
  has_password: boolean;
  // true bei Accounts, die sich über Google einloggen - steuert, ob der
  // E-Mail-Änderungsbereich in Account.tsx angezeigt wird.
  has_google_account: boolean;
  subscription_status: string | null;
  subscription_tier: string | null;
  trial_ends_at: string | null;
  free_checkins_used: number;
  onboarding_completed_at: string | null;
}
```

- [ ] **Step 2: Add the new api.auth methods**

In `frontend/src/api/client.ts`, inside the `auth: { ... }` object, add these methods right after `deleteAccount`:

```typescript
    changePassword: (currentPassword: string, newPassword: string) =>
      client.post("/auth/change-password", {
        current_password: currentPassword,
        new_password: newPassword,
      }),
    changeEmail: (newEmail: string, currentPassword: string) =>
      client.post("/auth/change-email", {
        new_email: newEmail,
        current_password: currentPassword,
      }),
    confirmEmailChange: (token: string) =>
      client
        .get<{ changed: boolean; new_email: string }>("/auth/confirm-email-change", {
          params: { token },
        })
        .then((r) => r.data),
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors (the new methods aren't used anywhere yet, so this just confirms the additions themselves are well-typed).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat: add change-password/change-email API client methods"
```

---

### Task 6: `ProfileSection` on Account.tsx

**Files:**
- Modify: `frontend/src/pages/Account.tsx`

- [ ] **Step 1: Add the `ProfileSection` component**

In `frontend/src/pages/Account.tsx`, add this new component right before `function DangerZoneSection()`:

```tsx
/** Zeigt E-Mail + Mitglied-seit-Datum, und - abhängig vom Account-Typ -
 * Formulare zum Ändern von Passwort und/oder E-Mail. Siehe Design-Spec
 * "Account-Profil-Verwaltung". */
function ProfileSection() {
  const { data: user } = useCurrentUser();
  const queryClient = useQueryClient();

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newPasswordConfirm, setNewPasswordConfirm] = useState("");
  const [passwordSuccess, setPasswordSuccess] = useState(false);

  const [newEmail, setNewEmail] = useState("");
  const [emailPassword, setEmailPassword] = useState("");
  const [emailRequested, setEmailRequested] = useState<string | null>(null);

  const changePasswordMutation = useMutation({
    mutationFn: () => api.auth.changePassword(currentPassword, newPassword),
    onSuccess: () => {
      setCurrentPassword("");
      setNewPassword("");
      setNewPasswordConfirm("");
      setPasswordSuccess(true);
    },
  });

  const changeEmailMutation = useMutation({
    mutationFn: () => api.auth.changeEmail(newEmail, emailPassword),
    onSuccess: () => {
      setEmailRequested(newEmail);
      setNewEmail("");
      setEmailPassword("");
      queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
    },
  });

  if (!user) return null;

  const passwordsMismatch =
    newPassword.length > 0 && newPasswordConfirm.length > 0 && newPassword !== newPasswordConfirm;

  const memberSince = new Date(user.created_at).toLocaleDateString("en-US", {
    month: "long",
    year: "numeric",
  });

  return (
    <>
      <Card>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="text-lg font-semibold text-white">{user.email}</p>
          <p className="text-sm text-slate-500">Member since {memberSince}</p>
        </div>
      </Card>

      {user.has_password && (
        <Card title="Change password">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setPasswordSuccess(false);
              if (!passwordsMismatch) changePasswordMutation.mutate();
            }}
            className="space-y-3"
          >
            <label className="flex flex-col gap-1 text-sm text-slate-400">
              Current password
              <input
                type="password"
                required
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-slate-400">
              New password
              <input
                type="password"
                required
                minLength={8}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-slate-400">
              Repeat new password
              <input
                type="password"
                required
                minLength={8}
                value={newPasswordConfirm}
                onChange={(e) => setNewPasswordConfirm(e.target.value)}
                className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
              />
            </label>
            {passwordsMismatch && (
              <p className="text-sm text-red-400">The new passwords don't match.</p>
            )}
            {changePasswordMutation.isError && (
              <p className="text-sm text-red-400">
                {(changePasswordMutation.error as any)?.response?.status === 401
                  ? "Current password is incorrect."
                  : "Could not change password."}
              </p>
            )}
            {passwordSuccess && <p className="text-sm text-accent">Password changed.</p>}
            <button
              type="submit"
              disabled={changePasswordMutation.isPending || passwordsMismatch}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-50"
            >
              {changePasswordMutation.isPending ? "Saving…" : "Change password"}
            </button>
          </form>
        </Card>
      )}

      {!user.has_google_account && (
        <Card title="Change email">
          {emailRequested ? (
            <p className="text-sm text-slate-300">
              Check your inbox at <span className="text-white">{emailRequested}</span> to confirm
              the change.
            </p>
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                changeEmailMutation.mutate();
              }}
              className="space-y-3"
            >
              <label className="flex flex-col gap-1 text-sm text-slate-400">
                New email address
                <input
                  type="email"
                  required
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm text-slate-400">
                Current password
                <input
                  type="password"
                  required
                  value={emailPassword}
                  onChange={(e) => setEmailPassword(e.target.value)}
                  className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
                />
              </label>
              {changeEmailMutation.isError && (
                <p className="text-sm text-red-400">
                  {(changeEmailMutation.error as any)?.response?.status === 401
                    ? "Current password is incorrect."
                    : (changeEmailMutation.error as any)?.response?.status === 409
                      ? "This email address is already in use."
                      : "Could not change email."}
                </p>
              )}
              <button
                type="submit"
                disabled={changeEmailMutation.isPending}
                className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-50"
              >
                {changeEmailMutation.isPending ? "Sending…" : "Change email"}
              </button>
            </form>
          )}
        </Card>
      )}
    </>
  );
}
```

- [ ] **Step 2: Mount it in the page**

In `frontend/src/pages/Account.tsx`, find the `export default function Account()` body:

```tsx
    <div className="mx-auto max-w-2xl space-y-6">
      <PageHeader title="Account" />

      <BillingSection />
```

Change it to mount `ProfileSection` right after `PageHeader`, before `BillingSection`:

```tsx
    <div className="mx-auto max-w-2xl space-y-6">
      <PageHeader title="Account" />

      <ProfileSection />

      <BillingSection />
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Account.tsx
git commit -m "feat: add profile header + password/email change forms to Account page"
```

---

### Task 7: `ConfirmEmailChange` public page + route

**Files:**
- Create: `frontend/src/pages/ConfirmEmailChange.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create the page**

Create `frontend/src/pages/ConfirmEmailChange.tsx`:

```tsx
import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { api } from "../api/client";

export default function ConfirmEmailChange() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");
  const [status, setStatus] = useState<"pending" | "success" | "error">("pending");
  const [newEmail, setNewEmail] = useState("");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      return;
    }
    api.auth
      .confirmEmailChange(token)
      .then((data) => {
        setNewEmail(data.new_email);
        setStatus("success");
      })
      .catch(() => setStatus("error"));
  }, [token]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-4 rounded-xl border border-white/5 bg-surface p-6 text-center">
        {status === "pending" && <p className="text-slate-400">Confirming…</p>}
        {status === "success" && (
          <>
            <h1 className="text-xl font-semibold text-white">Email updated!</h1>
            <p className="text-sm text-slate-400">
              Your login email is now <span className="text-white">{newEmail}</span>.
            </p>
            <Link to="/login" className="text-accent hover:underline text-sm">
              Continue
            </Link>
          </>
        )}
        {status === "error" && (
          <>
            <h1 className="text-xl font-semibold text-white">Invalid link</h1>
            <p className="text-sm text-slate-400">
              The link has expired or was already used.
            </p>
            <Link to="/login" className="text-accent hover:underline text-sm">
              Back to login
            </Link>
          </>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Register the route**

In `frontend/src/App.tsx`, add the import near the other page imports (right after `import VerifyEmail from "./pages/VerifyEmail";`):

```tsx
import ConfirmEmailChange from "./pages/ConfirmEmailChange";
```

Add the route right after the `/verify-email` route:

```tsx
      <Route path="/verify-email" element={<VerifyEmail />} />
      <Route path="/confirm-email-change" element={<ConfirmEmailChange />} />
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ConfirmEmailChange.tsx frontend/src/App.tsx
git commit -m "feat: add public email-change confirmation page and route"
```

---

### Task 8: Holistic review + finish branch

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all PASS except the pre-existing, unrelated `test_gemini_key_is_scoped_per_account` failure (confirm no NEW failures appeared).

- [ ] **Step 2: Run frontend type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 3: Manual review checklist**

Re-read every file touched by Tasks 1-7 end to end and confirm:
- `UserOut.created_at`/`has_google_account` match `CurrentUser.created_at`/`has_google_account` in `client.ts` exactly (same names, same JSON shape).
- The lightweight migration entry in `migrations.py` and the Alembic migration in `0004_email_token_new_email.py` add the exact same column (`email_tokens.new_email`, nullable string).
- `change-email`'s rate limiter, password check, and uniqueness check order matches the spec (password check before uniqueness check, so a wrong password never leaks whether an email is taken).
- `ProfileSection` correctly gates on `user.has_password` (password form) and `!user.has_google_account` (email form) independently - a coach with a password AND a Google login linked (edge case: user signed up with password, later the same email also got Google-linked) would see both, which is correct per spec (password form only cares about `has_password`, email form only cares about `has_google_account`).
- No leftover German strings in any new user-facing frontend text or backend error messages (this app is English-only per Stufe 5c).

- [ ] **Step 4: Use the finishing-a-development-branch skill**

Invoke `superpowers:finishing-a-development-branch` to merge/push per the user's standing "option 1" preference.
