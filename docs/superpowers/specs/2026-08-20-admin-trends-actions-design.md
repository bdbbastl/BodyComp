# Master-Admin: Signup-Trend & Admin-Aktionen — Design

## Ziel

Zwei Erweiterungen des Master-Admin-Bereichs in einem Durchlauf: (1) ein Signup-Verlaufs-Graph auf der Admin-Übersicht, (2) zwei Admin-Aktionen auf der Account-Detailseite (Passwort-Reset-Mail auslösen, freie Nachricht per E-Mail schicken).

## Teil 1: Signup-Trend-Graph

**Scope-Entscheidung:** Ursprünglich waren auch Churn-Rate und MRR-Verlauf angedacht. Beides erfordert historische Daten, die aktuell nirgends existieren (`User.subscription_status` speichert nur den aktuellen Stand, keine Historie; Stripe hat zwar echte Historie, aber ein Live-Abfragen über ALLE Kunden bei jedem Admin-Seitenaufruf wäre teuer). Beides bleibt daher **out of scope** für dieses Paket — Signup-Verlauf ist der einzige Trend, für den wir bereits echte Daten (`User.created_at`) ohne Zusatzaufwand haben.

**Graph:** Balkendiagramm "Signups — last 12 weeks" (Montag-Start-Wochen, wie bei den bestehenden Dashboard-Charts), direkt unter den bestehenden Kennzahl-Kacheln auf `/admin`. Neuer Wert `signups_per_week: list[{week_start: date, count: int}]` auf `AdminOverviewOut`, analog zur bereits vorhandenen `checkins_per_week`-Aggregation im Coach-Dashboard (gleiches Muster, andere Tabelle: `User` statt `CheckinSubmission`).

## Teil 2: Admin-Aktionen

**Scope-Entscheidung:** Account-Upgrade/-Downgrade wurde explizit ausgeschlossen — Abo-Änderungen bleiben ausschließlich über Stripe geregelt, kein manuelles Überschreiben von `subscription_tier`/`subscription_status` durch den Admin.

### a) Passwort-Reset-Mail auslösen

Neuer Button "Send password reset email" auf der Account-Detailseite. Löst denselben Flow aus wie der bestehende "Forgot password?"-Link (`POST /api/auth/forgot-password`): ein Reset-Token wird erzeugt, die Standard-Reset-Mail (`send_password_reset_email`) geht an den User raus. Der Admin sieht/setzt zu keinem Zeitpunkt ein Passwort. Die gemeinsame Logik wird aus `routers/auth.py`'s `forgot_password()` in eine neue Funktion `trigger_password_reset(db: Session, user: User) -> None` in `services/account.py` extrahiert, damit beide Aufrufer (öffentlicher Endpunkt + Admin-Endpunkt) dieselbe Implementierung nutzen — kein dupliziertes Token-Handling. Neuer Endpunkt `POST /api/admin/accounts/{user_id}/send-password-reset`.

Kein Enumeration-Schutz nötig (anders als beim öffentlichen `forgot-password`-Endpunkt) — der Admin ist bereits eingeloggt und kennt den Account, den er gerade ansieht. Accounts ohne eigenes Passwort (Google-only, `password_hash is None`) bekommen keine Mail — Button ist deaktiviert mit Hinweistext "Account uses Google Sign-In", analog zur bestehenden Logik in `forgot_password()`.

### b) Nachricht an Nutzer schicken

Neues Textfeld + "Send message"-Button auf der Account-Detailseite. Admin schreibt freien Text, wird als E-Mail an den User verschickt — kein neues In-App-Benachrichtigungssystem, nutzt den bereits vorhandenen Resend-E-Mail-Versand. Neue Funktion `send_admin_message_email(*, to: str, message: str) -> None` in `services/email.py`, folgt dem bestehenden Muster der anderen `send_*_email`-Funktionen dort. Neuer Endpunkt `POST /api/admin/accounts/{user_id}/send-message` mit Body `{message: str}` (min. 1, max. 2000 Zeichen). Kein Erfolgs-Tracking/Verlauf gespeicherter Nachrichten in dieser Version — reiner Fire-and-forget-Versand, wie bei den bestehenden System-Mails.

Beide Endpunkte liegen unter dem bestehenden `router = APIRouter(prefix="/api/admin", ..., dependencies=[Depends(require_admin)])` und erben damit automatisch den Admin-Check.

## Out of Scope

- Churn-Rate- und MRR-Verlaufs-Graphen (siehe Teil 1) — eigenes späteres Paket, sobald eine Entscheidung für historisches Tracking getroffen ist.
- Account-Upgrade/-Downgrade durch den Admin — bleibt exklusiv über Stripe.
- In-App-Benachrichtigungssystem — Nachrichten gehen nur per E-Mail raus.
- Verlauf/Historie versendeter Admin-Nachrichten oder ausgelöster Passwort-Resets — kein Audit-Log in dieser Version.
