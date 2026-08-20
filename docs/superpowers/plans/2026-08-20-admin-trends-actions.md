# Admin Signup Trend & Admin Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 12-week signup trend chart to the Master-Admin overview, and two admin actions (trigger a password-reset email, send a free-text email) on the account-detail page.

**Architecture:** The trend chart is a pure aggregation added to the existing `GET /api/admin/overview` response, following the same `WeekCount`-style pattern already used for the coach dashboard's weekly chart. The password-reset action extracts the existing `forgot-password` endpoint's core logic into a shared `services/account.py` function so both the public endpoint and the new admin endpoint use identical, un-duplicated token logic. The message action reuses the existing Resend email-sending pattern (`services/email.py`), with HTML-escaping since it embeds free admin-authored text.

**Tech Stack:** FastAPI + SQLAlchemy (backend), React + TanStack Query + TypeScript + Tailwind (frontend), pytest with `monkeypatch` for email mocking (matching the existing pattern in `tests/test_admin_router.py`/`tests/test_signup.py`).

---

### Task 1: Signup trend chart data on the admin overview endpoint

**Files:**
- Modify: `backend/app/schemas/admin.py`
- Modify: `backend/app/routers/admin.py`
- Test: `backend/tests/test_admin_router.py`

- [ ] **Step 1: Add the response model**

In `backend/app/schemas/admin.py`, add this class and extend `AdminOverviewOut`:

```python
class AdminWeekCount(BaseModel):
    week_start: str  # ISO date (Monday) "YYYY-MM-DD"
    count: int
```

Replace:

```python
class AdminOverviewOut(BaseModel):
    total_accounts: int
    single_accounts: int
    coach_accounts: int
    active_subscriptions: int
    signups_this_week: int
    signups_this_month: int
```

with:

```python
class AdminOverviewOut(BaseModel):
    total_accounts: int
    single_accounts: int
    coach_accounts: int
    active_subscriptions: int
    signups_this_week: int
    signups_this_month: int
    signups_per_week: list[AdminWeekCount]
```

- [ ] **Step 2: Write the failing test**

Append to `backend/tests/test_admin_router.py`:

```python
def test_overview_includes_signups_per_week(client, db_session):
    admin = _make_user(db_session, email="admin7@example.com", is_admin=True)
    _login_as(client, admin)

    response = client.get("/api/admin/overview")
    assert response.status_code == 200
    weeks = response.json()["signups_per_week"]
    assert len(weeks) == 12
    # admin selbst wurde gerade erst angelegt -> aktuelle Woche hat mind. 1
    assert weeks[-1]["count"] >= 1
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_admin_router.py::test_overview_includes_signups_per_week -v`
Expected: FAIL — pydantic `ValidationError: Field required` for `signups_per_week`.

- [ ] **Step 4: Implement the aggregation**

In `backend/app/routers/admin.py`, add `AdminWeekCount` to the existing `from app.schemas.admin import (...)` block, then inside `overview(...)`, right before the final `return AdminOverviewOut(...)` statement, insert:

```python
    current_week_start = now.date() - timedelta(days=now.weekday())
    signups_per_week = []
    for weeks_ago in range(11, -1, -1):
        week_start = current_week_start - timedelta(weeks=weeks_ago)
        week_end = week_start + timedelta(days=7)
        count = (
            db.query(func.count(User.id))
            .filter(User.created_at >= week_start, User.created_at < week_end)
            .scalar()
            or 0
        )
        signups_per_week.append(AdminWeekCount(week_start=week_start.isoformat(), count=count))
```

Then update the return statement to add the new field:

```python
    return AdminOverviewOut(
        total_accounts=total_accounts,
        single_accounts=single_accounts,
        coach_accounts=coach_accounts,
        active_subscriptions=active_subscriptions,
        signups_this_week=signups_this_week,
        signups_this_month=signups_this_month,
        signups_per_week=signups_per_week,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_admin_router.py -v`
Expected: all pass.

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all pass aside from the known unrelated flaky `test_gemini_key_is_scoped_per_account`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/admin.py backend/app/routers/admin.py backend/tests/test_admin_router.py
git commit -m "feat: add 12-week signup trend to admin overview"
```

---

### Task 2: Extract password-reset logic, add admin password-reset endpoint

**Files:**
- Modify: `backend/app/services/account.py`
- Modify: `backend/app/routers/auth.py`
- Modify: `backend/app/routers/admin.py`
- Test: `backend/tests/test_admin_router.py`
- Test: `backend/tests/test_signup.py` (verify the refactor didn't break the existing forgot-password flow)

- [ ] **Step 1: Read the current `forgot_password` implementation**

Run: `grep -n "def forgot_password" -A 20 backend/app/routers/auth.py`

Confirm the exact current body before editing (shown below is what it should look like, but verify against the live file in case it has diverged).

- [ ] **Step 2: Extract the shared function**

In `backend/app/services/account.py`, add these imports at the top (extend the existing `from sqlalchemy.orm import Session` block — add alongside it):

```python
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.models.email_token import EmailToken, EmailTokenPurpose
from app.services.auth import create_email_token, hash_email_token
from app.services.email import send_password_reset_email
```

Then add this function at the end of the file:

```python
def trigger_password_reset(db: Session, user: User) -> None:
    """Erzeugt einen Reset-Token und verschickt die Standard-Reset-Mail -
    gemeinsame Logik für den öffentlichen forgot-password-Endpunkt
    (routers/auth.py) und den Admin-Endpunkt POST
    /admin/accounts/{id}/send-password-reset (siehe Design-Spec
    "Master-Admin: Signup-Trend & Admin-Aktionen" Abschnitt 2a). Kein
    Enumeration-Schutz nötig - der Aufrufer ist entweder der öffentliche
    Endpunkt (prüft selbst, ob der Account existiert) oder der bereits
    eingeloggte Admin (kennt den Account schon)."""
    raw_token = create_email_token(user_id=user.id, purpose=EmailTokenPurpose.RESET_PASSWORD.value)
    db.add(
        EmailToken(
            user_id=user.id,
            token_hash=hash_email_token(raw_token),
            purpose=EmailTokenPurpose.RESET_PASSWORD,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )
    db.commit()
    reset_url = f"{settings.frontend_base_url}/reset-password?token={raw_token}"
    send_password_reset_email(to=user.email, reset_url=reset_url)
```

- [ ] **Step 3: Update `forgot_password` to use the shared function**

In `backend/app/routers/auth.py`, replace the body of `forgot_password`:

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
```

with:

```python
@router.post("/forgot-password", status_code=204)
def forgot_password(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(forgot_password_rate_limit),
):
    user = db.query(User).filter(User.email == payload.email).first()
    if user is not None and user.password_hash is not None:
        trigger_password_reset(db, user)
    # immer 204 - kein Enumeration-Leak, egal ob Account existiert/Passwort hat
```

Add the import at the top of `backend/app/routers/auth.py` (extend the existing `from app.services.account import create_account` line — check if `services.account` is already imported; if so, add `trigger_password_reset` to that import line, otherwise add a new import line):

```python
from app.services.account import create_account, trigger_password_reset
```

- [ ] **Step 4: Run the existing signup/password-reset tests to confirm the refactor didn't break anything**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_signup.py -v`
Expected: all pass (this file already has forgot-password-adjacent tests — the refactor must not change behavior).

If `test_signup.py` doesn't have forgot-password tests, instead run: `cd backend && .venv/Scripts/python -m pytest -k forgot_password -v` to find and run whichever test file covers it, and confirm it passes.

- [ ] **Step 5: Write the failing tests for the new admin endpoint**

Append to `backend/tests/test_admin_router.py`:

```python
def test_admin_send_password_reset_triggers_email(client, db_session, monkeypatch):
    admin = _make_user(db_session, email="admin8@example.com", is_admin=True)
    target = _make_user(db_session, email="target-reset@example.com")
    _login_as(client, admin)

    sent = {}

    def _fake_send(*, to, reset_url):
        sent["to"] = to
        sent["reset_url"] = reset_url

    monkeypatch.setattr("app.services.account.send_password_reset_email", _fake_send)

    response = client.post(f"/api/admin/accounts/{target.id}/send-password-reset")
    assert response.status_code == 204
    assert sent["to"] == "target-reset@example.com"
    assert "reset-password?token=" in sent["reset_url"]


def test_admin_send_password_reset_rejects_google_only_account(client, db_session):
    from app.models.user import AccountType

    admin = _make_user(db_session, email="admin9@example.com", is_admin=True)
    google_user = User(
        email="google-only@example.com",
        password_hash=None,
        display_name="Google User",
        account_type=AccountType.SINGLE,
    )
    db_session.add(google_user)
    db_session.commit()
    db_session.refresh(google_user)
    _login_as(client, admin)

    response = client.post(f"/api/admin/accounts/{google_user.id}/send-password-reset")
    assert response.status_code == 400
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_admin_router.py -k send_password_reset -v`
Expected: FAIL — 404 (route doesn't exist yet).

- [ ] **Step 7: Implement the admin endpoint**

In `backend/app/routers/admin.py`, add `trigger_password_reset` to the imports (extend the existing `from app.services.account import ...` line if present, otherwise add):

```python
from app.services.account import trigger_password_reset
```

Add the endpoint, right after `get_account_billing`:

```python
@router.post("/accounts/{user_id}/send-password-reset", status_code=204)
def send_account_password_reset(user_id: int, db: Session = Depends(get_db)):
    """Löst dieselbe Reset-Mail aus wie der öffentliche forgot-password-
    Endpunkt (siehe services/account.py trigger_password_reset) - der
    Admin sieht/setzt zu keinem Zeitpunkt ein Passwort."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Account not found")
    if user.password_hash is None:
        raise HTTPException(400, "This account uses Google Sign-In and has no password to reset")
    trigger_password_reset(db, user)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_admin_router.py -v`
Expected: all pass.

- [ ] **Step 9: Run the full backend suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all pass aside from the known unrelated flaky test.

- [ ] **Step 10: Commit**

```bash
git add backend/app/services/account.py backend/app/routers/auth.py backend/app/routers/admin.py backend/tests/test_admin_router.py
git commit -m "feat: extract password-reset logic, add admin password-reset action"
```

---

### Task 3: Admin "send message" email action

**Files:**
- Modify: `backend/app/schemas/admin.py`
- Modify: `backend/app/services/email.py`
- Modify: `backend/app/routers/admin.py`
- Test: `backend/tests/test_admin_router.py`

- [ ] **Step 1: Add the request schema**

In `backend/app/schemas/admin.py`, add at the end of the file:

```python
class AdminSendMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
```

Add `Field` to the existing `from pydantic import BaseModel` import line at the top of the file (change it to `from pydantic import BaseModel, Field`).

- [ ] **Step 2: Add the email-sending function**

In `backend/app/services/email.py`, add `from html import escape` to the imports at the top of the file (alongside the existing `import resend`).

Then add this function, right after `send_password_reset_email`:

```python
def send_admin_message_email(*, to: str, message: str) -> None:
    """Freier Text vom Admin an einen Nutzer - siehe Design-Spec
    "Master-Admin: Signup-Trend & Admin-Aktionen" Abschnitt 2b. message
    wird escaped, bevor es ins HTML eingebettet wird (es ist
    Admin-eingegebener Freitext, kein von uns kontrollierter String) -
    Zeilenumbrüche werden danach manuell durch <br> ersetzt, damit die
    Formatierung des Admins erhalten bleibt."""
    safe_message = escape(message).replace("\n", "<br>")
    html = _base_email_html(
        "A message from your coach team",
        f"""
        <p>{safe_message}</p>
        """,
    )
    resend.Emails.send({
        "from": settings.email_from_address,
        "to": [to],
        "subject": "A message from BodyComp Tracker",
        "html": html,
    })
```

- [ ] **Step 3: Write the failing tests**

Append to `backend/tests/test_admin_router.py`:

```python
def test_admin_send_message_emails_user(client, db_session, monkeypatch):
    admin = _make_user(db_session, email="admin10@example.com", is_admin=True)
    target = _make_user(db_session, email="target-message@example.com")
    _login_as(client, admin)

    sent = {}

    def _fake_send(*, to, message):
        sent["to"] = to
        sent["message"] = message

    monkeypatch.setattr("app.routers.admin.send_admin_message_email", _fake_send)

    response = client.post(
        f"/api/admin/accounts/{target.id}/send-message", json={"message": "Hello there!"}
    )
    assert response.status_code == 204
    assert sent["to"] == "target-message@example.com"
    assert sent["message"] == "Hello there!"


def test_admin_send_message_rejects_empty_message(client, db_session):
    admin = _make_user(db_session, email="admin11@example.com", is_admin=True)
    target = _make_user(db_session, email="target-message2@example.com")
    _login_as(client, admin)

    response = client.post(f"/api/admin/accounts/{target.id}/send-message", json={"message": ""})
    assert response.status_code == 422


def test_admin_send_message_404_for_missing_account(client, db_session):
    admin = _make_user(db_session, email="admin12@example.com", is_admin=True)
    _login_as(client, admin)

    response = client.post("/api/admin/accounts/999999/send-message", json={"message": "Hi"})
    assert response.status_code == 404
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_admin_router.py -k send_message -v`
Expected: FAIL — 404 (route doesn't exist yet).

- [ ] **Step 5: Implement the endpoint**

In `backend/app/routers/admin.py`, add `send_admin_message_email` and `AdminSendMessageRequest` to the existing imports (extend `from app.services.email import ...` if present, else add a new line; extend the `from app.schemas.admin import (...)` block):

```python
from app.services.email import send_admin_message_email
```

Add `AdminSendMessageRequest` to the `from app.schemas.admin import (...)` block.

Add the endpoint, right after `send_account_password_reset`:

```python
@router.post("/accounts/{user_id}/send-message", status_code=204)
def send_account_message(
    user_id: int, payload: AdminSendMessageRequest, db: Session = Depends(get_db)
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Account not found")
    send_admin_message_email(to=user.email, message=payload.message)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_admin_router.py -v`
Expected: all pass.

- [ ] **Step 7: Run the full backend suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all pass aside from the known unrelated flaky test.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/admin.py backend/app/services/email.py backend/app/routers/admin.py backend/tests/test_admin_router.py
git commit -m "feat: add admin send-message-to-user email action"
```

---

### Task 4: Frontend — signup trend chart on the admin overview

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/pages/Admin.tsx`

- [ ] **Step 1: Add the type**

In `frontend/src/types/index.ts`, find the `AdminOverview` interface:

```typescript
export interface AdminOverview {
  total_accounts: number;
  single_accounts: number;
  coach_accounts: number;
  active_subscriptions: number;
  signups_this_week: number;
```

Read the full existing interface first to confirm its exact current shape (it should also have `signups_this_month: number`). Add a new field `signups_per_week: { week_start: string; count: number }[];` to it.

- [ ] **Step 2: Add the chart component**

In `frontend/src/pages/Admin.tsx`, add this component at the end of the file:

```tsx
function SignupTrendChart({ weeks }: { weeks: { week_start: string; count: number }[] }) {
  const max = Math.max(1, ...weeks.map((w) => w.count));
  return (
    <Card title="Signups — last 12 weeks">
      <div className="flex h-20 items-end gap-2">
        {weeks.map((w) => (
          <div key={w.week_start} className="flex flex-1 flex-col items-center gap-1">
            <div
              className="w-full rounded-t bg-accent/60"
              style={{ height: `${Math.max(4, (w.count / max) * 100)}%` }}
              title={`${w.count} signups`}
            />
          </div>
        ))}
      </div>
    </Card>
  );
}
```

- [ ] **Step 3: Render it below the existing overview grid**

In `frontend/src/pages/Admin.tsx`, find the closing `</div>` of the existing overview grid:

```tsx
        {overviewQuery.data && (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            <Card title="Total Accounts">
```

Read the full block to find its matching closing `</div>` (it ends with a `Signups (7d / 30d)` card, then closes). Right after that closing `</div>` and still inside the `{overviewQuery.data && (...)}` conditional, add:

```tsx
            <SignupTrendChart weeks={overviewQuery.data.signups_per_week} />
```

So the resulting structure is: `{overviewQuery.data && ( <> <div className="grid ...">...</div> <SignupTrendChart weeks={overviewQuery.data.signups_per_week} /> </> )}` — wrap in a React fragment (`<>...</>`) since there are now two sibling elements instead of one.

- [ ] **Step 4: Verify the frontend type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/pages/Admin.tsx
git commit -m "feat: show signup trend chart on admin overview"
```

---

### Task 5: Frontend — password-reset and send-message actions on account detail

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/AdminAccountDetail.tsx`

- [ ] **Step 1: Add the API client methods**

In `frontend/src/api/client.ts`, inside the `admin` object, add (alongside the existing `setAccountActive`/`getBilling` methods):

```typescript
    sendPasswordReset: (userId: number) =>
      client.post(`/admin/accounts/${userId}/send-password-reset`),
    sendMessage: (userId: number, message: string) =>
      client.post(`/admin/accounts/${userId}/send-message`, { message }),
```

- [ ] **Step 2: Add the password-reset button**

In `frontend/src/pages/AdminAccountDetail.tsx`, inside `export default function AdminAccountDetail()`, add this mutation right after the existing `toggleActiveMutation`:

```tsx
  const sendPasswordResetMutation = useMutation({
    mutationFn: () => api.admin.sendPasswordReset(userIdNum),
  });
```

Find the existing "Deactivate account"/"Reactivate account" button inside `<Card title="Account">` and add the new button right after it (still inside the Card, after the existing button's closing `</button>`):

```tsx
          <button
            onClick={() => sendPasswordResetMutation.mutate()}
            disabled={sendPasswordResetMutation.isPending || !account.has_password}
            title={!account.has_password ? "This account uses Google Sign-In" : undefined}
            className="mt-2 rounded-lg border border-white/15 px-4 py-2 text-sm font-medium text-white hover:bg-white/5 disabled:opacity-40"
          >
            {sendPasswordResetMutation.isPending
              ? "Sending…"
              : sendPasswordResetMutation.isSuccess
                ? "Reset email sent"
                : "Send password reset email"}
          </button>
```

`AdminAccountOut`/`AdminAccountDetail` doesn't currently expose whether the account has a password — check `frontend/src/types/index.ts`'s `AdminAccount` interface: if it has no `has_password` field, the backend's `AdminAccountOut` schema also doesn't expose one (only `CurrentUser` does, from a different endpoint) — in that case, drop the `!account.has_password` condition from `disabled` and the `title` attribute entirely (the button stays always-enabled; the backend's 400 response with a clear message is the actual safety net if the account turns out to be Google-only, and the mutation's error state can show that message — see Step 3).

- [ ] **Step 3: Show an error message if the password-reset call fails**

Right after the button from Step 2, add:

```tsx
          {sendPasswordResetMutation.isError && (
            <p className="mt-1 text-xs text-red-400">
              {(sendPasswordResetMutation.error as any)?.response?.data?.detail ??
                "Could not send the reset email."}
            </p>
          )}
```

- [ ] **Step 4: Add the send-message form**

Add this new component at the end of `frontend/src/pages/AdminAccountDetail.tsx`:

```tsx
function SendMessageCard({ userId }: { userId: number }) {
  const [message, setMessage] = useState("");
  const sendMessageMutation = useMutation({
    mutationFn: () => api.admin.sendMessage(userId, message),
    onSuccess: () => setMessage(""),
  });

  return (
    <Card title="Send message">
      <textarea
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        rows={4}
        maxLength={2000}
        placeholder="Write a message to this user…"
        className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white focus:border-accent focus:outline-none"
      />
      <div className="mt-2 flex items-center gap-2">
        <button
          type="button"
          onClick={() => sendMessageMutation.mutate()}
          disabled={sendMessageMutation.isPending || message.trim() === ""}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-40"
        >
          {sendMessageMutation.isPending ? "Sending…" : "Send message"}
        </button>
        {sendMessageMutation.isSuccess && (
          <span className="text-xs text-emerald-400">Sent</span>
        )}
      </div>
      {sendMessageMutation.isError && (
        <p className="mt-1 text-xs text-red-400">Could not send the message.</p>
      )}
    </Card>
  );
}
```

Add `useState` to the existing React imports at the top of the file if not already present (check the current import line — this file already uses hooks, but confirm `useState` specifically is imported; if not, add it to the existing `import { useState } from "react";`-style line or add a new one).

Render `<SendMessageCard userId={userIdNum} />` right after `<BillingCard userId={userIdNum} />`, still inside the `<div className="mx-auto max-w-3xl space-y-6">` wrapper.

- [ ] **Step 5: Verify the frontend type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Manual check in the browser**

Log in as an admin, open an account's detail page. Verify: "Send password reset email" button exists and shows "Reset email sent" after clicking (with the backend running — check via network tab or by receiving the actual email in dev). "Send message" card has a textarea + button, sending clears the textarea and shows "Sent".

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/pages/AdminAccountDetail.tsx
git commit -m "feat: add password-reset and send-message actions to admin account detail"
```

---

### Task 6: Final review and finish

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all tests pass except the pre-existing unrelated flaky `test_gemini_key_is_scoped_per_account`.

- [ ] **Step 2: Run the full frontend type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Use superpowers:finishing-a-development-branch**

Follow that skill to present merge/PR/keep/discard options and complete the branch.
