# App-Übersetzung Deutsch → Englisch (Stufe 5c) — Design-Spec

**Datum:** 2026-08-17
**Status:** Genehmigt

## Kontext

Die App ist bisher komplett auf Deutsch (Frontend-Texte, Backend-Fehlermeldungen, E-Mail-Templates, Rechtstexte-Platzhalter). Ziel: kompletter, dauerhafter Ersatz durch Englisch — keine Sprachumschaltung (i18n-Infrastruktur explizit nicht gewünscht), reiner Text-Ersatz.

Eingeplant als **Stufe 5c**, direkt nach Stufe 5b (Onboarding-Flow).

## Ziel

Jeder Text, den ein Nutzer jemals sehen könnte, ist auf Englisch:
- Alle Frontend-UI-Texte (Labels, Buttons, Platzhalter, Fehlermeldungen, Seitentitel)
- Alle Backend-Fehlermeldungen, die im Frontend angezeigt werden (`HTTPException`-Detail-Strings)
- Alle transaktionalen E-Mail-Templates
- Rechtstexte-Platzhalterseiten (Impressum/Datenschutz/AGB - Inhalt bleibt Platzhalter, aber der Platzhalter-Hinweistext selbst wird englisch)

## Explizit NICHT im Scope

- Code-Kommentare (bleiben Deutsch, reine Entwickler-Dokumentation)
- Dateien unter `docs/superpowers/` (Specs, Pläne)
- Variablen-/Funktions-/Klassennamen, DB-Spalten-/Tabellennamen
- Interne Log-Messages (`logger.warning(...)` etc. - nicht user-sichtbar)
- Git-Commit-Messages
- Keine i18n-Infrastruktur, kein Sprachumschalter - reiner, dauerhafter Text-Ersatz

## Architektur-Entscheidung

Rein mechanische Textänderung ohne Logik-/Verhaltensänderung. Keine neue Abhängigkeit (kein `react-i18next` o.ä. - würde eine Umschaltbarkeit implizieren, die explizit nicht gewünscht ist).

## Vorgehen

### 1. Scope-Ermittlung

Vor der Task-Aufteilung: vollständiger Grep-Sweep über die betroffenen Verzeichnisse, um alle Dateien mit deutschen nutzer-sichtbaren Strings zu katalogisieren:
- `frontend/src/pages/**/*.tsx`
- `frontend/src/components/**/*.tsx`
- `backend/app/routers/**/*.py` (HTTPException-Messages)
- `backend/app/services/email.py` (E-Mail-Templates)
- `backend/app/schemas/**/*.py` (falls custom Validierungsfehler)

### 2. Task-Aufteilung nach Bereich

Da es sich um eine reine Textänderung über viele Dateien handelt (nicht um neue Logik), werden die Implementierungs-Tasks NICHT mit exaktem Vorher/Nachher-Code je String vorgeschrieben (unpraktikabel bei diesem Umfang), sondern pro Bereich mit der Anweisung "übersetze alle nutzer-sichtbaren deutschen Strings in diesen Dateien 1:1 sinngemäß nach Englisch, Code-Struktur/Kommentare/Namen bleiben unverändert":

- Auth-Flow (Login, Signup, VerifyEmail, ForgotPassword, ResetPassword, SignupSuccess)
- Dashboard, Account, Settings
- Timeline, Unprocessed, Compare, Statistics
- Public Check-in Flow (CheckinSubmit, ClientCheckins)
- Legal-Platzhalterseiten
- Gemeinsame Komponenten (AppShell, ClientShell, PageHeader, EmptyState, UpgradeBanner, Card, Skeleton)
- Backend: alle Router (HTTPException-Messages)
- Backend: E-Mail-Templates (`services/email.py`)

### 3. Review

Jeder Task wird wie gewohnt review-t (Spec-Compliance: wurden alle Strings im Bereich erfasst, nichts an Logik/Struktur verändert + stichprobenartiger Wortlaut-/Ton-Check auf natürliches Englisch statt wörtlicher Übersetzung).

### 4. Konsistenz-Glossar

Ein paar wiederkehrende Begriffe werden einheitlich übersetzt, um Konsistenz über alle Tasks hinweg sicherzustellen:
- "Klient/Kunde" → "client"
- "Check-in" → "check-in" (bleibt, ist bereits englisches Lehnwort)
- "Coach" → "coach" (bleibt)
- "Abo" → "subscription"
- "Kontingent" → "quota" / "allowance"
- "Einreichung" → "submission"
- "Anzeige-Einstellungen" → "Display settings"

## Testing-Ansatz

- Backend: bestehende Tests, die auf exakte deutsche Fehlermeldungs-Strings prüfen (z.B. `assert "Klienten-Limit erreicht" in ...`), müssen auf die neuen englischen Strings angepasst werden - das ist Teil jedes Backend-Tasks, nicht optional
- Frontend: `npx tsc --noEmit` zur Typsicherheit (Textänderungen ändern keine Typen, aber sicherheitshalber)
- Keine neuen Tests nötig (reine Textänderung, keine neue Logik)
