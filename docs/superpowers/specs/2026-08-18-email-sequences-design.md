# E-Mail-Sequenzen (Stufe 5e) — Design-Spec

**Datum:** 2026-08-18
**Status:** Genehmigt

## Kontext

Drei fehlende Lifecycle-E-Mails wurden beim Erst-Brainstorming von Stufe 4 (Billing) als sinnvoll identifiziert, aber bewusst zurückgestellt: Willkommens-Mail, Trial-Ende-Erinnerung, Kontingent-Nudge.

## Ziel

Alle drei E-Mails ergänzen, nach dem bestehenden Muster in `backend/app/services/email.py` (Resend, best-effort - ein Mail-Fehler darf den eigentlichen Vorgang nie rückgängig machen oder blockieren).

## Design im Detail

### 1. Willkommens-Mail

- Neues Template `send_welcome_email(*, to: str, display_name: str) -> None`
- Ausgelöst in `routers/auth.py`, Endpunkt `verify_email` - direkt nachdem `email_verified_at` **erstmals** gesetzt wurde (nicht bei einem erneuten Aufruf mit bereits verifizierter Adresse - der bestehende Code muss dafür bereits zwischen "wird gerade zum ersten Mal verifiziert" und "war schon verifiziert" unterscheiden, das als Bedingung für den Mail-Versand nutzen)
- Inhalt: kurze Begrüßung, Link zur App (`{frontend_base_url}/`)

### 2. Trial-Ende-Erinnerung

- Neuer Webhook-Handler-Zweig in `routers/billing.py` für das Stripe-Event `customer.subscription.trial_will_end` (feuert bei Stripe standardmäßig 3 Tage vor Trial-Ende)
- Neues Template `send_trial_ending_email(*, to: str, days_left: int, plan_name: str) -> None`
- Nur für Coach-Accounts relevant - ergibt sich automatisch, da nur Coach-Abos einen Trial haben (Single-Accounts nutzen das Kontingent-Modell ohne Trial)
- Inhalt: "Deine Testphase endet in X Tagen", Link zur Account-Seite

**Voraussetzung außerhalb des Codes:** Der Nutzer muss `customer.subscription.trial_will_end` in Stripe (Test- UND Live-Modus, beide Railway-Environments) manuell am bestehenden Webhook-Endpoint hinzufügen - das ist keine Code-Änderung und kann nicht automatisiert werden. Wird im README-Abschnitt "Stripe-Setup" ergänzt.

### 3. Kontingent-Nudge

- In `services/billing.py`, Funktion `check_and_consume_free_checkin`: nach dem erfolgreichen atomaren Increment (`db.refresh(user)`) prüfen, ob `user.free_checkins_used == FREE_CHECKINS_LIMIT - 1` (= nach dem 1. von 2 Check-ins) - wenn ja, `send_quota_warning_email(to=user.email)` auslösen
- Neues Template `send_quota_warning_email(*, to: str) -> None`
- Passiert durch die kumulative, nie sinkende Zähler-Logik automatisch nur genau einmal pro Account - kein zusätzlicher Idempotenz-Mechanismus nötig
- Inhalt: "Noch 1 kostenloser Check-in übrig", Link zum Abo (Account-Seite)

## Out of Scope

- Keine weiteren Lifecycle-Mails über die drei genannten hinaus (z. B. Re-Engagement-Mails für inaktive Nutzer)
- Keine E-Mail-Präferenzen/Opt-out-Einstellungen (bestehende E-Mails haben das auch nicht)
- Keine Änderung an bestehenden E-Mail-Templates

## Testing-Ansatz

- Backend: Unit-Tests für jeden neuen Trigger-Punkt, analog zu den bestehenden Tests für `send_checkin_submitted_email`/`send_checkin_reminder_email` (Mock via `monkeypatch`, prüft dass die Funktion mit den richtigen Argumenten aufgerufen wird, nicht den tatsächlichen Mailversand)
- Explizite Idempotenz-Tests: `verify_email` zweimal mit demselben Token/bereits verifizierter Mail aufrufen → Welcome-Mail nur beim ersten Mal; `check_and_consume_free_checkin` zweimal aufrufen (Kontingent 2→1→0) → Nudge nur beim Übergang zu "1 übrig", nicht nochmal beim letzten Verbrauch
