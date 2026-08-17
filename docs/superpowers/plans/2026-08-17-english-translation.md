# App-Übersetzung Deutsch → Englisch (Stufe 5c) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jeder Text, den ein Nutzer jemals sieht, wird von Deutsch auf Englisch umgestellt - Frontend-UI, Backend-Fehlermeldungen, E-Mail-Templates, Rechtstexte-Platzhalter. Reiner Text-Ersatz, keine i18n-Infrastruktur, keine Logikänderung.

**Architecture:** Rein mechanische Textänderung pro Bereich (Datei-Gruppe). Code-Kommentare, Variablennamen, `docs/superpowers/`-Inhalte bleiben unangetastet. Da es sich um Textänderungen über sehr viele Stellen handelt, geben die Tasks unten NICHT jede einzelne Übersetzung wortwörtlich vor (unpraktikabel bei diesem Umfang) - stattdessen: exakte Dateiliste pro Task + Glossar für konsistente Begriffe + die Anweisung, jeden nutzer-sichtbaren deutschen String sinngemäß natürlich (nicht wörtlich) ins Englische zu übertragen.

**Tech Stack:** React/TypeScript (Frontend), FastAPI/Python (Backend) - keine neuen Abhängigkeiten.

## Glossar (in JEDEM Task konsistent zu verwenden)

| Deutsch | Englisch |
|---|---|
| Klient/Kunde | client |
| Check-in | check-in |
| Coach | coach |
| Abo | subscription |
| Kontingent | quota / allowance |
| Einreichung | submission |
| Anzeige-Einstellungen | Display settings |
| Kontotyp | Account type |
| Testphase | Trial |
| Einloggen/Anmelden | Log in / Sign in |
| Registrieren | Sign up |

## Was NICHT übersetzt wird (in jedem Task zu beachten)

- Code-Kommentare (bleiben Deutsch)
- Variablen-/Funktions-/Klassennamen, DB-Spalten-/Tabellennamen
- Interne Log-Messages (`logger.warning(...)` etc.)
- `docs/superpowers/`-Dateien

---

### Task 1: Auth-Flow-Seiten

**Files:**
- Modify: `frontend/src/pages/Login.tsx`
- Modify: `frontend/src/pages/Signup.tsx`
- Modify: `frontend/src/pages/SignupSuccess.tsx`
- Modify: `frontend/src/pages/VerifyEmail.tsx`
- Modify: `frontend/src/pages/ForgotPassword.tsx`
- Modify: `frontend/src/pages/ResetPassword.tsx`

- [ ] **Step 1: Alle nutzer-sichtbaren deutschen Strings übersetzen**

In allen 6 Dateien: jeden JSX-Textinhalt, jedes Label, jeden Placeholder, jede Fehlermeldung, jeden Button-Text von Deutsch auf natürliches Englisch übersetzen. Code-Struktur, Kommentare, Variablennamen, CSS-Klassen bleiben unverändert - nur die Strings selbst ändern sich.

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler

- [ ] **Step 3: Grep-Check auf verbliebenes Deutsch**

Run: `grep -rn "ä\|ö\|ü\|ß" frontend/src/pages/Login.tsx frontend/src/pages/Signup.tsx frontend/src/pages/SignupSuccess.tsx frontend/src/pages/VerifyEmail.tsx frontend/src/pages/ForgotPassword.tsx frontend/src/pages/ResetPassword.tsx`
Expected: nur noch Treffer in Code-Kommentaren (auf Deutsch-Umlaute in Kommentarzeilen prüfen, keine JSX-Textinhalte mehr)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Login.tsx frontend/src/pages/Signup.tsx frontend/src/pages/SignupSuccess.tsx frontend/src/pages/VerifyEmail.tsx frontend/src/pages/ForgotPassword.tsx frontend/src/pages/ResetPassword.tsx
git commit -m "feat: translate auth flow pages to English"
```

---

### Task 2: Dashboard, Account, Settings

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`
- Modify: `frontend/src/pages/Account.tsx`
- Modify: `frontend/src/pages/Settings.tsx`

- [ ] **Step 1: Alle nutzer-sichtbaren deutschen Strings übersetzen**

Gleiches Vorgehen wie Task 1. Besonders beachten: `Account.tsx` enthält die `COACH_PLANS`-Preistabelle (Feature-Bullet-Listen) und die Billing-Texte - alle übersetzen, inkl. der Plan-Namen bleiben (Starter/Pro/Business sind bereits Englisch) aber die Beschreibungstexte darunter übersetzen. `Settings.tsx` enthält die kürzlich (2026-08-17) hinzugefügte Single-Account-Unterscheidung ("Erinnere mich..." vs "Erinnerung...") - beide Varianten übersetzen.

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler

- [ ] **Step 3: Grep-Check**

Run: `grep -rn "ä\|ö\|ü\|ß" frontend/src/pages/Dashboard.tsx frontend/src/pages/Account.tsx frontend/src/pages/Settings.tsx`
Expected: nur noch Kommentare

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx frontend/src/pages/Account.tsx frontend/src/pages/Settings.tsx
git commit -m "feat: translate dashboard, account, and settings pages to English"
```

---

### Task 3: Timeline, Unprocessed, Compare, Statistics

**Files:**
- Modify: `frontend/src/pages/Timeline.tsx`
- Modify: `frontend/src/pages/Unprocessed.tsx`
- Modify: `frontend/src/pages/Compare.tsx`
- Modify: `frontend/src/pages/Statistics.tsx`

- [ ] **Step 1: Alle nutzer-sichtbaren deutschen Strings übersetzen**

Gleiches Vorgehen. Beachten: `Timeline.tsx` hat Datumsformatierung über `formatDateWithWeek` (in `frontend/src/utils/date.ts`) - falls dort deutsche Wochentags-/Monatsnamen fest codiert sind (z.B. `toLocaleDateString("de-DE")`), diese Datei ebenfalls in diesem Task auf `"en-US"` (oder `"en-GB"`, konsistent mit dem Rest der App wählen - `en-US` empfohlen) umstellen und zu den zu committenden Files hinzufügen. Alle `toLocaleDateString("de-DE")`/`toLocaleString("de-DE")`-Aufrufe in den 4 Haupt-Dateien selbst ebenfalls auf `"en-US"` umstellen.

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler

- [ ] **Step 3: Grep-Check**

Run: `grep -rn "ä\|ö\|ü\|ß\|de-DE" frontend/src/pages/Timeline.tsx frontend/src/pages/Unprocessed.tsx frontend/src/pages/Compare.tsx frontend/src/pages/Statistics.tsx frontend/src/utils/date.ts`
Expected: nur noch Kommentare, keine `de-DE`-Locale-Strings mehr

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Timeline.tsx frontend/src/pages/Unprocessed.tsx frontend/src/pages/Compare.tsx frontend/src/pages/Statistics.tsx frontend/src/utils/date.ts
git commit -m "feat: translate timeline, unprocessed, compare, statistics pages to English"
```

---

### Task 4: Public Check-in Flow

**Files:**
- Modify: `frontend/src/pages/CheckinSubmit.tsx`
- Modify: `frontend/src/pages/ClientCheckins.tsx`

- [ ] **Step 1: Alle nutzer-sichtbaren deutschen Strings übersetzen**

Gleiches Vorgehen. `CheckinSubmit.tsx` ist die öffentliche, unauthentifizierte Seite (Magic Link) - besonders wichtig, da sie auch von Nicht-Coaches (den Klienten selbst) gesehen wird. `toLocaleDateString("de-DE")`/`toLocaleString("de-DE")`-Aufrufe ebenfalls auf `"en-US"` umstellen.

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`

- [ ] **Step 3: Grep-Check**

Run: `grep -rn "ä\|ö\|ü\|ß\|de-DE" frontend/src/pages/CheckinSubmit.tsx frontend/src/pages/ClientCheckins.tsx`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/CheckinSubmit.tsx frontend/src/pages/ClientCheckins.tsx
git commit -m "feat: translate public check-in flow to English"
```

---

### Task 5: Legal-Platzhalterseiten

**Files:**
- Modify: `frontend/src/pages/legal/Agb.tsx`
- Modify: `frontend/src/pages/legal/Datenschutz.tsx`
- Modify: `frontend/src/pages/legal/Impressum.tsx`
- Modify: `frontend/src/pages/legal/LegalPagePlaceholder.tsx`

- [ ] **Step 1: Platzhalter-Hinweistexte übersetzen**

Diese Seiten sind bewusst noch Platzhalter (echter Rechtstext folgt später, siehe frühere Stufen) - nur den Platzhalter-Hinweistext selbst übersetzen ("Diese Seite ist noch nicht final..." o.ä.), nicht versuchen, echten Rechtsinhalt zu erfinden. Die Datei-/Routennamen (`/agb`, `/datenschutz`, `/impressum`) bleiben unverändert - das sind URL-Pfade, keine sichtbaren Texte, eine Änderung würde nur bestehende Links/Bookmarks brechen ohne Nutzen (Out-of-Scope laut Design-Spec).

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/legal/
git commit -m "feat: translate legal placeholder pages to English"
```

---

### Task 6: Gemeinsame Komponenten

**Files:**
- Modify: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/components/ClientShell.tsx`
- Modify: `frontend/src/components/ClientRedirect.tsx`
- Modify: `frontend/src/components/RequireAuth.tsx`
- Modify: `frontend/src/components/PageHeader.tsx`
- Modify: `frontend/src/components/EmptyState.tsx` (Aufrufstellen in den Pages sind bereits Task 1-4, hier nur die Komponente selbst falls dort Text hartcodiert ist)
- Modify: `frontend/src/components/UpgradeBanner.tsx`
- Modify: `frontend/src/components/Card.tsx`
- Modify: `frontend/src/components/Skeleton.tsx`
- Modify: `frontend/src/components/OnboardingModal.tsx`
- Modify: `frontend/src/components/OnboardingTooltip.tsx`
- Modify: `frontend/src/contexts/OnboardingContext.tsx`

- [ ] **Step 1: Alle nutzer-sichtbaren deutschen Strings übersetzen**

`OnboardingModal.tsx`/`OnboardingTooltip.tsx`/`OnboardingContext.tsx` sind bereits komplett auf Englisch (wurden bei ihrer Erstellung in Stufe 5b bereits englisch geschrieben, siehe Plan `2026-08-17-onboarding-flow.md`) - hier nur gegenprüfen, nicht blind nochmal durcharbeiten. `UpgradeBanner.tsx`s Default-Prop `ctaLabel = "Jetzt upgraden"` auf Englisch übersetzen; die eigentlichen `message`-Texte kommen von den Aufrufstellen (Dashboard.tsx/AppShell.tsx - bereits in anderen Tasks abgedeckt).

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`

- [ ] **Step 3: Grep-Check**

Run: `grep -rln "ä\|ö\|ü\|ß" frontend/src/components/ frontend/src/contexts/`
Expected: nur noch Dateien mit reinen Kommentar-Treffern (händisch stichprobenartig prüfen)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ frontend/src/contexts/
git commit -m "feat: translate shared components to English"
```

---

### Task 7: Backend - alle Router (HTTPException-Messages)

**Files:**
- Modify: `backend/app/routers/auth.py`
- Modify: `backend/app/routers/billing.py`
- Modify: `backend/app/routers/checkins.py`
- Modify: `backend/app/routers/clients.py`
- Modify: `backend/app/routers/comparisons.py`
- Modify: `backend/app/routers/day_logs.py`
- Modify: `backend/app/routers/photos.py`
- Modify: `backend/app/routers/poses.py`
- Modify: `backend/app/routers/public_checkin.py`
- Modify: `backend/app/routers/settings.py`
- Modify: `backend/app/services/billing.py` (die `HTTPException`-Messages darin, z.B. "Klienten-Limit erreicht...")
- Test: alle Testdateien unter `backend/tests/`, die auf exakte deutsche Fehlermeldungs-Strings prüfen

- [ ] **Step 1: Alle `HTTPException(...)`-Detail-Strings übersetzen**

In allen genannten Dateien: jeden `raise HTTPException(<code>, "<deutscher Text>")`-Aufruf auf Englisch übersetzen. NICHT übersetzen: Docstrings, Kommentare, Log-Messages (`logger.warning(...)` etc.).

- [ ] **Step 2: Betroffene Tests finden**

Run: `grep -rln "Klienten-Limit\|Kontingent\|Nicht eingeloggt\|E-Mail\|Passwort\|ungültig\|abgelaufen\|erreicht" backend/tests/`

Für jede gefundene Testdatei: die Assertions, die auf den EXAKTEN deutschen Fehlertext prüfen (z.B. `assert "Klienten-Limit erreicht" in response.json()["detail"]` oder `assert response.json()["detail"] == "..."`), auf den neuen englischen Text anpassen - exakt den Text verwenden, den du in Step 1 für die jeweilige Stelle gewählt hast (Konsistenz zwischen Code und Test).

- [ ] **Step 3: Volle Backend-Testsuite laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: alle Tests grün (bis auf den bekannten, unabhängigen `test_gemini_key_is_scoped_per_account`-Fall bei lokal gesetztem `.env`-Key)

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/ backend/app/services/billing.py backend/tests/
git commit -m "feat: translate backend error messages to English"
```

---

### Task 8: Backend - E-Mail-Templates

**Files:**
- Modify: `backend/app/services/email.py`
- Test: betroffene Tests, die auf E-Mail-Inhalte prüfen (falls vorhanden - `grep -rln "send_.*_email" backend/tests/` zum Finden)

- [ ] **Step 1: Alle 4 E-Mail-Templates übersetzen**

`send_verification_email`, `send_password_reset_email`, `send_checkin_submitted_email`, `send_checkin_reminder_email` - Betreffzeile UND Body-Text jeweils auf natürliches Englisch übersetzen. Ton beibehalten (freundlich, kurz, wie bisher).

- [ ] **Step 2: Tests prüfen/anpassen**

Falls Tests auf exakten deutschen E-Mail-Text prüfen (unwahrscheinlich, die meisten testen vermutlich nur `to`/`client_name` via Mock, siehe Pattern in `test_checkin_reminders.py`/`test_public_checkin_router.py` aus früheren Stufen) - falls doch, entsprechend anpassen.

- [ ] **Step 3: Tests laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: alle grün (gleiche bekannte Ausnahme wie oben)

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/email.py backend/tests/
git commit -m "feat: translate email templates to English"
```

---

### Task 9: Backend - Schemas (Pydantic-Feldbeschreibungen/Custom-Validierung, falls vorhanden)

**Files:**
- Modify: `backend/app/schemas/auth.py`
- Modify: `backend/app/schemas/checkin.py`
- Modify: `backend/app/schemas/photo.py`
- Modify: `backend/app/schemas/settings.py`
- Modify: `backend/app/schemas/signup.py`
- Modify: `backend/app/schemas/billing.py`
- Modify: `backend/app/schemas/client.py`

- [ ] **Step 1: Deutsche Strings in Schemas übersetzen**

Diese Dateien enthalten überwiegend reine Typdefinitionen ohne nutzer-sichtbaren Text - der Grep-Sweep hat sie trotzdem gefunden, wahrscheinlich wegen deutscher DOCSTRINGS/Kommentare (NICHT übersetzen, siehe Scope). Durchsuche jede Datei gezielt nach eventuellen `Field(..., description="...")`-Pydantic-Feldbeschreibungen oder Custom-`@field_validator`-Fehlermeldungen mit deutschem Text (diese landen ggf. in der API-Fehlerantwort und sind damit nutzer-sichtbar) - NUR diese übersetzen, Docstrings/Kommentare unverändert lassen. Falls eine Datei bei genauer Durchsicht NUR Kommentare/Docstrings auf Deutsch hat und keine echten nutzer-sichtbaren Strings, in diesem Task nichts ändern (nicht künstlich Änderungen erzwingen).

- [ ] **Step 2: Tests laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest -q`

- [ ] **Step 3: Commit** (nur falls tatsächlich etwas geändert wurde)

```bash
git add backend/app/schemas/
git commit -m "feat: translate user-facing schema strings to English"
```

---

### Task 10: Finaler Review + Branch abschließen

- [ ] **Step 1: Vollständigen Grep-Sweep über die ganze App**

Run:
```bash
grep -rn "ä\|ö\|ü\|ß" frontend/src/pages frontend/src/components frontend/src/contexts backend/app/routers backend/app/services --include="*.tsx" --include="*.ts" --include="*.py"
```
Jeden verbleibenden Treffer durchgehen: ist es ein Code-Kommentar (OK, bleibt) oder doch noch ein übersehener nutzer-sichtbarer String (muss nachgezogen werden)?

- [ ] **Step 2: Vollständigen Typecheck laufen lassen**

Run: `cd frontend && npx tsc --noEmit`
Expected: keine Fehler

- [ ] **Step 3: Backend-Testsuite laufen lassen**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: alle Tests grün (bis auf den bekannten unabhängigen Gemini-Key-Fall)

- [ ] **Step 4: Manuelle Gesamt-Durchsicht**

Kompletten Flow einmal durchklicken (Signup → Verify → Login → Dashboard → Klient anlegen → Timeline/Compare/Settings → Account → Logout, plus den öffentlichen Check-in-Flow) und bestätigen, dass wirklich alles Englisch ist, inkl. Fehlermeldungen (z.B. absichtlich eine falsche Eingabe machen, um eine Backend-Fehlermeldung zu triggern).

- [ ] **Step 5: `superpowers:finishing-a-development-branch` nutzen**

Tests verifizieren (bereits in Step 2/3 geschehen), Merge nach `dev` anbieten, danach `dev`→`main` nur nach expliziter Nutzer-Bestätigung.
