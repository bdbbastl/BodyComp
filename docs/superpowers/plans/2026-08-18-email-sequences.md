# E-Mail-Sequenzen (Stufe 5e) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drei neue Lifecycle-E-Mails: Willkommens-Mail nach Verifizierung, Trial-Ende-Erinnerung (Stripe-Webhook), Kontingent-Nudge bei "noch 1 Check-in übrig".

**Architecture:** Drei neue Template-Funktionen in `services/email.py` nach bestehendem Muster, drei neue Auslösepunkte in bereits existierendem Code (kein neuer Router/Endpoint nötig).

**Tech Stack:** FastAPI, Resend, Stripe-Webhooks.

---

### Task 1: Neue E-Mail-Templates

**Files:**
- Modify: `backend/app/services/email.py`
- Test: `backend/tests/test_email_service.py`

- [ ] **Step 1: Drei neue Template-Funktionen ergänzen**

Nach der bestehenden `send_checkin_reminder_email`-Funktion:

```python
def send_welcome_email(*, to: str, display_name: str) -> None:
    html = _base_email_html(
        f"Welcome, {display_name}!",
        """
        <p>Your account is verified and ready to go.</p>
        <p><a href="{app_url}">Open BodyComp Tracker</a></p>
        """.replace("{app_url}", settings.frontend_base_url),
    )
    resend.Emails.send({
        "from": settings.email_from_address,
        "to": [to],
        "subject": "Welcome to BodyComp Tracker",
        "html": html,
    })


def send_trial_ending_email(*, to: str, days_left: int, plan_name: str) -> None:
    day_word = "day" if days_left == 1 else "days"
    html = _base_email_html(
        "Your trial is ending soon",
        f"""
        <p>Your {plan_name} trial ends in {days_left} {day_word}. Add a payment method to
        keep your subscription active without interruption.</p>
        <p><a href="{settings.frontend_base_url}/account">Manage your subscription</a></p>
        """,
    )
    resend.Emails.send({
        "from": settings.email_from_address,
        "to": [to],
        "subject": "Your trial is ending soon - BodyComp Tracker",
        "html": html,
    })


def send_quota_warning_email(*, to: str) -> None:
    html = _base_email_html(
        "1 free check-in left",
        f"""
        <p>You've used your first free check-in. You have <strong>1 free check-in left</strong>
        before you'll need to subscribe to keep tracking.</p>
        <p><a href="{settings.frontend_base_url}/account">See plans</a></p>
        """,
    )
    resend.Emails.send({
        "from": settings.email_from_address,
        "to": [to],
        "subject": "1 free check-in left - BodyComp Tracker",
        "html": html,
    })
```

- [ ] **Step 2: Tests schreiben**

In `backend/tests/test_email_service.py` (Datei existiert bereits laut vorheriger Stufe - bestehende Tests dort als Vorbild für Mock-Pattern nehmen, vermutlich wird `resend.Emails.send` gemockt):

```python
def test_send_welcome_email_calls_resend_with_correct_subject(monkeypatch):
    sent = []
    monkeypatch.setattr("app.services.email.resend.Emails.send", lambda payload: sent.append(payload))

    send_welcome_email(to="max@example.com", display_name="Max")

    assert sent[0]["to"] == ["max@example.com"]
    assert "Welcome" in sent[0]["subject"]


def test_send_trial_ending_email_includes_days_left(monkeypatch):
    sent = []
    monkeypatch.setattr("app.services.email.resend.Emails.send", lambda payload: sent.append(payload))

    send_trial_ending_email(to="coach@example.com", days_left=3, plan_name="Pro")

    assert "3 days" in sent[0]["html"]
    assert "Pro" in sent[0]["html"]


def test_send_quota_warning_email_calls_resend(monkeypatch):
    sent = []
    monkeypatch.setattr("app.services.email.resend.Emails.send", lambda payload: sent.append(payload))

    send_quota_warning_email(to="single@example.com")

    assert sent[0]["to"] == ["single@example.com"]
```

(Import-Zeile am Dateianfang ergänzen: `from app.services.email import send_quota_warning_email, send_trial_ending_email, send_welcome_email` - exakten Import-Stil der Datei übernehmen.)

- [ ] **Step 3: Tests laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest -q tests/test_email_service.py`
Expected: alle PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/email.py backend/tests/test_email_service.py
git commit -m "feat: add welcome, trial-ending, and quota-warning email templates"
```

---

### Task 2: Willkommens-Mail nach Verifizierung

**Files:**
- Modify: `backend/app/routers/auth.py`
- Test: `backend/tests/test_auth_router.py`

- [ ] **Step 1: Auslösung in `verify_email`**

In `backend/app/routers/auth.py`, Import ergänzen: `from app.services.email import send_welcome_email` (prüfen, ob `email`-Service-Importe schon anders benannt in dieser Datei vorkommen, z.B. `from app.services.email import send_verification_email` - dann konsistent im selben Import-Statement ergänzen).

Die `verify_email`-Funktion ändern von:

```python
    user = db.get(User, payload["user_id"])
    user.email_verified_at = datetime.now(timezone.utc)
    token_row.used_at = datetime.now(timezone.utc)
    db.commit()
    return {"verified": True}
```

zu (Welcome-Mail nur beim ERSTEN Mal, siehe Design-Spec Abschnitt 1 - `already_verified` muss VOR dem Setzen von `email_verified_at` geprüft werden):

```python
    user = db.get(User, payload["user_id"])
    already_verified = user.email_verified_at is not None
    user.email_verified_at = datetime.now(timezone.utc)
    token_row.used_at = datetime.now(timezone.utc)
    db.commit()

    if not already_verified:
        try:
            send_welcome_email(to=user.email, display_name=user.display_name)
        except Exception:
            logger.warning("Could not send welcome email", exc_info=True)

    return {"verified": True}
```

Prüfen, ob `logger` bereits in dieser Datei definiert ist (`logger = logging.getLogger(__name__)`, wie in anderen Routern üblich) - falls nicht, ergänzen (`import logging` + die Zeile), analog zum Muster in `routers/public_checkin.py`.

- [ ] **Step 2: Test schreiben**

In `backend/tests/test_auth_router.py`, existierenden Test für `verify_email` als Vorbild nehmen (Token-Erzeugung, Login-Helper) und ergänzen:

```python
def test_verify_email_sends_welcome_email_only_once(client, db_session, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.routers.auth.send_welcome_email", lambda **kwargs: sent.append(kwargs)
    )
    # Signup + Token-Erzeugung nach dem exakten Muster der bestehenden
    # test_verify_email-Tests in dieser Datei übernehmen, nicht neu erfinden.
    ...
    response1 = client.get(f"/api/auth/verify-email?token={token}")
    assert response1.status_code == 200
    assert len(sent) == 1

    # Zweiter Verifizierungsversuch mit frischem Token (z.B. via
    # resend-verification) darf die Mail nicht nochmal auslösen.
    ...
```

(Der genaue Testaufbau - wie ein gültiges Token in dieser Testdatei erzeugt wird - muss aus den bestehenden `test_verify_email_*`-Tests derselben Datei übernommen werden, nicht neu erfunden.)

- [ ] **Step 3: Tests laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest -q tests/test_auth_router.py`
Expected: alle PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/auth.py backend/tests/test_auth_router.py
git commit -m "feat: send welcome email on first successful email verification"
```

---

### Task 3: Trial-Ende-Erinnerung (Stripe-Webhook)

**Files:**
- Modify: `backend/app/routers/billing.py`
- Test: `backend/tests/test_billing_router.py`

- [ ] **Step 1: Neuer Webhook-Zweig für `customer.subscription.trial_will_end`**

In `backend/app/routers/billing.py`, Import ergänzen: `from app.services.email import send_trial_ending_email` und `import logging` + `logger = logging.getLogger(__name__)` (falls nicht schon vorhanden - prüfen).

Nach dem bestehenden `elif event_type == "customer.subscription.deleted":`-Block einen weiteren `elif`-Zweig ergänzen:

```python
    elif event_type == "customer.subscription.trial_will_end":
        user = db.query(User).filter(User.stripe_customer_id == obj["customer"]).first()
        if user is not None:
            try:
                trial_end = obj["trial_end"]
            except KeyError:
                trial_end = None
            days_left = 3  # Stripe feuert dieses Event standardmaessig genau 3 Tage vorher
            if trial_end:
                delta = datetime.fromtimestamp(trial_end, tz=timezone.utc) - datetime.now(timezone.utc)
                days_left = max(1, round(delta.total_seconds() / 86400))
            plan_name = (user.subscription_tier or "").capitalize() or "subscription"
            try:
                send_trial_ending_email(to=user.email, days_left=days_left, plan_name=plan_name)
            except Exception:
                logger.warning("Could not send trial-ending email", exc_info=True)
```

(`datetime`/`timezone` sind in dieser Datei bereits importiert, siehe bestehender `trial_end`-Umgang im `customer.subscription.updated`-Zweig - denselben `[]`/try-except-Zugriffsstil auf das Stripe-SDK-Objekt übernehmen, KEIN `.get()`, siehe Kommentar im bestehenden Code dazu.)

- [ ] **Step 2: Test schreiben**

In `backend/tests/test_billing_router.py`, bestehende Webhook-Tests (`test_webhook_updates_subscription_status_on_update_event` o.ä.) als Vorbild nehmen:

```python
def test_webhook_sends_trial_ending_email(client, db_session, monkeypatch):
    from datetime import datetime, timedelta, timezone

    sent = []
    monkeypatch.setattr(
        "app.routers.billing.send_trial_ending_email", lambda **kwargs: sent.append(kwargs)
    )

    user = User(
        email="coach@example.com", password_hash=hash_password("pw12345"), display_name="Coach",
        email_verified_at=datetime.now(timezone.utc), stripe_customer_id="cus_trial_test",
        subscription_tier="starter",
    )
    db_session.add(user)
    db_session.commit()

    trial_end_ts = int((datetime.now(timezone.utc) + timedelta(days=3)).timestamp())
    fake_event = {
        "type": "customer.subscription.trial_will_end",
        "data": {"object": {"customer": "cus_trial_test", "trial_end": trial_end_ts}},
    }
    monkeypatch.setattr(
        "app.routers.billing.stripe.Webhook.construct_event", lambda *a, **kw: fake_event
    )

    response = client.post(
        "/api/billing/webhook", content=b"{}", headers={"stripe-signature": "fake"}
    )
    assert response.status_code == 204
    assert sent[0]["to"] == "coach@example.com"
    assert sent[0]["days_left"] == 3
```

(Exakten `_login`/Helper-Stil und Imports dieser Testdatei übernehmen - siehe bestehende Webhook-Tests direkt darüber/darunter in derselben Datei.)

- [ ] **Step 3: Tests laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest -q tests/test_billing_router.py`
Expected: alle PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/billing.py backend/tests/test_billing_router.py
git commit -m "feat: send trial-ending email on Stripe trial_will_end webhook"
```

---

### Task 4: Kontingent-Nudge

**Files:**
- Modify: `backend/app/services/billing.py`
- Test: `backend/tests/test_billing_service.py`

- [ ] **Step 1: Auslösung in `check_and_consume_free_checkin`**

In `backend/app/services/billing.py`, Import ergänzen: `from app.services.email import send_quota_warning_email` und `import logging` + `logger = logging.getLogger(__name__)` (falls nicht schon vorhanden).

Die Funktion ändern von:

```python
    if result.rowcount == 0:
        raise HTTPException(
            402,
            "Free allowance used up - please subscribe to submit more check-ins.",
        )
    db.flush()
    db.refresh(user)
```

zu:

```python
    if result.rowcount == 0:
        raise HTTPException(
            402,
            "Free allowance used up - please subscribe to submit more check-ins.",
        )
    db.flush()
    db.refresh(user)

    # Nudge genau beim Uebergang zu "noch 1 uebrig" - dank des nie
    # sinkenden, kumulativen Zaehlers passiert das automatisch nur genau
    # einmal pro Account, kein zusaetzlicher Idempotenz-Mechanismus
    # noetig. Siehe Design-Spec "E-Mail-Sequenzen" Abschnitt 3.
    if user.free_checkins_used == FREE_CHECKINS_LIMIT - 1:
        try:
            send_quota_warning_email(to=user.email)
        except Exception:
            logger.warning("Could not send quota-warning email", exc_info=True)
```

- [ ] **Step 2: Test schreiben**

In `backend/tests/test_billing_service.py`, bestehende Tests für `check_and_consume_free_checkin` als Vorbild nehmen:

```python
def test_sends_quota_warning_email_after_first_free_checkin(db_session, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.billing.send_quota_warning_email", lambda **kwargs: sent.append(kwargs)
    )
    user = _make_user(db_session, email="single@b.com", account_type=AccountType.SINGLE)

    check_and_consume_free_checkin(user, db_session)  # 1. Check-in
    assert len(sent) == 1
    assert sent[0]["to"] == "single@b.com"

    check_and_consume_free_checkin(user, db_session)  # 2. Check-in - kein weiterer Nudge
    assert len(sent) == 1
```

(`_make_user`-Helper existiert bereits in dieser Testdatei, siehe bestehende Tests direkt darüber.)

- [ ] **Step 3: Tests laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest -q tests/test_billing_service.py`
Expected: alle PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/billing.py backend/tests/test_billing_service.py
git commit -m "feat: send quota-warning email after first free check-in"
```

---

### Task 5: README-Hinweis für den manuellen Stripe-Setup-Schritt

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Ergänzung im bestehenden "Stripe-Setup (Stufe 4)"-Abschnitt**

Im Unterabschnitt zur Webhook-Konfiguration einen Hinweis ergänzen, dass zusätzlich zu den bisherigen 3 Events (`customer.subscription.created/updated/deleted`) jetzt auch `customer.subscription.trial_will_end` am Webhook-Endpoint abonniert werden muss (Stripe Dashboard → Entwickler → Webhooks → Endpoint → Events bearbeiten), sowohl im Test- als auch im Live-Modus, für beide Railway-Environments (Staging + Production) getrennt konfiguriert.

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: note trial_will_end webhook event requirement"
```

---

### Task 6: Finaler Review + Branch abschließen

- [ ] **Step 1: Backend-Testsuite laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: alle Tests grün (bis auf den bekannten, unabhängigen `test_gemini_key_is_scoped_per_account`-Fall bei lokal gesetztem `.env`-Key)

- [ ] **Step 2: Manuelle Durchsicht**

Alle drei neuen Code-Pfade nochmal im Zusammenhang lesen: Willkommens-Mail-Trigger in `auth.py`, Trial-Webhook-Zweig in `billing.py`, Kontingent-Nudge in `services/billing.py` - keine der drei darf einen bestehenden Ablauf (Verifizierung, Webhook-Verarbeitung, Check-in-Erstellung) blockieren, falls der Mailversand fehlschlägt (alle drei nutzen `try/except` + Logging, kein `raise`).

- [ ] **Step 3: `superpowers:finishing-a-development-branch` nutzen**

Tests verifizieren (bereits in Step 1 geschehen), Merge nach `dev` anbieten (inkl. Push nach origin), danach `dev`→`main` nur nach expliziter Nutzer-Bestätigung.
