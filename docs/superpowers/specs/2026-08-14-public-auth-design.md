# Design-Spec: Public Auth (Stufe 2)

## Kontext

Stufe 1 (Mandantenfähigkeit) ist abgeschlossen: mehrere Coach-Accounts,
Session-Cookie-Auth, Client-Verwaltung. Registrierung passierte bisher
ausschließlich manuell/per Migrationsscript — es gibt **keine öffentliche
Registrierung, keine E-Mail-Verifizierung, keinen Passwort-Reset**.

Dieses Dokument spezifiziert **Stufe 2** aus dem in Stufe 1 festgelegten
4-Stufen-Plan:

1. Mandantenfähigkeit ✅ (abgeschlossen)
2. **Public Auth** (dieses Dokument) — Self-Signup, E-Mail-Verifizierung,
   Passwort-Reset, Google OAuth, DSGVO-Grundlagen
3. Produktions-Hosting — SQLite → Postgres, lokales Filesystem →
   Object-Storage (S3-kompatibel). *Eigene Spec.*
4. Payment/Billing — Stripe-Anbindung, Pläne/Limits. *Eigene Spec.*

Die App läuft weiterhin nur lokal — Stufe 3 macht sie erst öffentlich
erreichbar. Stufe 2 baut den Auth-*Mechanismus* vollständig fertig, damit er
funktioniert, sobald gehostet wird; Dinge, die eine echte öffentliche
Domain/Skalierung voraussetzen (z.B. Resend-Domain-Verifizierung, verteiltes
Rate-Limiting), werden bewusst auf Stufe 3 verschoben.

## Vorab-Aufgaben (vor der eigentlichen Umsetzung)

Zwei kleine, unabhängige Aufräumarbeiten, bevor Stufe 2 losgeht:

1. **Migrations-Code entfernen**: `app/core/migrate_to_multitenancy.py`,
   `app/core/migrate_legacy_unique_constraints.py`, ihre Tests, und der
   Aufruf in `main.py`'s `lifespan()` — die einmalige Migration ist bereits
   erfolgreich gegen die echte Produktions-DB gelaufen und wird nie wieder
   gebraucht.
2. **`Client.age` → `Client.birth_date`**: Das Feld "Alter" (Zahl) wird
   durch "Geburtsdatum" (Datum, mit Datepicker im Frontend) ersetzt. Alter
   lässt sich bei Bedarf daraus berechnen.

## Architektur-Entscheidung

**Ansatz: selbst gebaut, direkt in die bestehende Stufe-1-Architektur
integriert.** Kein Wechsel auf einen externen Auth-as-a-Service (Auth0,
Clerk, Supabase Auth) — das würde die gerade erst gebaute
Session-Cookie-Logik aus Stufe 1 größtenteils verwerfen und ist für den
Umfang "E-Mail+Passwort + optional Google" überdimensioniert.

Neue Dependencies:
- `authlib` — übernimmt den Google-OAuth-Flow (PKCE, State-Param-CSRF-Schutz,
  Token-Exchange, ID-Token-Validierung). Wird nicht selbst nachgebaut.
- `resend` (Python-SDK) — transaktionaler E-Mail-Versand.

## Datenmodell

`User` bekommt neue Spalten (alle nullable bzw. mit sinnvollem Default):

```python
google_id: str | None          # unique, indexed - Googles `sub`-Claim
email_verified_at: datetime | None   # NULL = nicht bestätigt
privacy_accepted_at: datetime | None # Nachweis der Datenschutz-Zustimmung
```

`password_hash` wird **nullable** — ein rein über Google registrierter
Account hat kein eigenes Passwort.

Neue Tabelle `EmailToken`:

```python
class EmailToken(Base):
    __tablename__ = "email_tokens"
    id: int (PK)
    user_id: int (FK -> users.id, ondelete=CASCADE)
    token_hash: str            # gehashter Token, nicht der Klartext-Link
    purpose: Enum("verify_email", "reset_password")
    expires_at: datetime
    used_at: datetime | None   # verhindert Zweitverwendung
```

Der eigentliche Link-Token wird signiert (`itsdangerous`, wie bereits bei
Sessions in Stufe 1) und nur gehasht in der DB gespeichert — ein DB-Leak
gibt damit keine gültigen Links preis.

`User` bekommt zusätzlich `sessions_invalidated_at: datetime | None` —
nach einem Passwort-Reset gesetzt, `get_current_user` prüft das
Session-Cookie-Ausstellungsdatum dagegen und invalidiert ältere Sessions.

## Registrierung per E-Mail + Passwort

```
POST /api/auth/signup  { email, password, display_name, privacy_accepted: true }
```

- `privacy_accepted` muss `true` sein (sonst 422) — Pflicht-Checkbox im
  Frontend, ohne Haken kein Absenden möglich.
- Legt einen `User` an über den bestehenden `create_account`-Service aus
  Stufe 1 (legt automatisch den einen `Client` mit an) —
  `password_hash` gesetzt, `email_verified_at = NULL`,
  `privacy_accepted_at = jetzt`, `account_type = single` (Standard).
- Erzeugt einen `EmailToken` (purpose="verify_email", 24h gültig), schickt
  per Resend eine Bestätigungsmail mit Link
  (`https://.../verify-email?token=...`).
- Rate-limited (siehe eigener Abschnitt).

```
GET /api/auth/verify-email?token=...
```

- Validiert Token (Signatur, `expires_at`, `used_at IS NULL`), setzt
  `email_verified_at = jetzt`, markiert Token als benutzt, redirected ins
  Frontend auf eine Erfolgsseite.
- Ungültiger/abgelaufener/bereits benutzter Token → Fehlerseite mit Option,
  eine neue Bestätigungsmail anzufordern.

```
POST /api/auth/resend-verification  { email }
```

- Rate-limited. Antwortet immer generisch (kein Enumeration-Leak).

**Hartes Verifizierungs-Gate**: `POST /api/auth/login` prüft zusätzlich
`email_verified_at IS NOT NULL` — sonst 403 mit klarer Fehlermeldung. Google-
Accounts sind immer sofort verifiziert (siehe unten), betrifft also nur
E-Mail+Passwort-Accounts.

## Google OAuth

```
GET  /api/auth/google/login     -> redirect zu Googles Consent-Screen
GET  /api/auth/google/callback  -> Google redirected hierher zurück
```

Beim Callback (via `authlib`):

1. Code gegen Googles ID-Token tauschen, Signatur/Audience automatisch
   validiert, liefert `sub`, `email`, `email_verified`, `name`.
2. `User` mit `google_id == sub` suchen:
   - **Gefunden** → Session-Cookie setzen, fertig.
   - **Nicht gefunden, aber `email` matched bestehenden User** → `google_id`
     wird automatisch an diesen Account angehängt (Google bestätigt die
     E-Mail-Inhaberschaft), danach einloggen. Nutzer kann sich danach mit
     beidem einloggen.
   - **Kein Match** → neuer `User` via `create_account`, aber
     `password_hash = NULL`, `google_id = sub`,
     `email_verified_at = jetzt` (sofort bestätigt), `display_name` aus
     Googles `name`-Feld (im Account-Bereich danach editierbar),
     `privacy_accepted_at = jetzt` (Zustimmung gilt implizit mit der
     Weiterleitung zu Google als erteilt — analog zu vielen bestehenden
     OAuth-Flows; Consent-Text wird auf der Google-Login-Seite vor dem
     Redirect angezeigt).
3. Redirect zurück ins Frontend (Dashboard bzw. bestehende
   `ClientRedirect`-Logik aus Stufe 1).

Ein Google-only-Account (kein Passwort gesetzt) kann sich **nicht** über
den normalen Login-Endpunkt mit einem Passwort einloggen — das Frontend
zeigt in dem Fall eine passende Fehlermeldung statt "falsches Passwort".

## Passwort-Reset

```
POST /api/auth/forgot-password  { email }
```

- Falls ein User mit dieser E-Mail existiert **und** ein Passwort gesetzt
  hat (kein Google-only-Account): `EmailToken` (purpose="reset_password",
  1h gültig), Mail mit Reset-Link raus.
- Antwortet **immer** generisch ("Falls ein Account existiert, wurde eine
  Mail geschickt") — kein Enumeration-Leak, gleiches Prinzip wie beim
  Login-Fehler in Stufe 1.
- Rate-limited.

```
POST /api/auth/reset-password  { token, new_password }
```

- Validiert Token wie bei der E-Mail-Bestätigung, setzt neuen
  `password_hash`, markiert Token benutzt, setzt
  `sessions_invalidated_at = jetzt` (invalidiert alle bestehenden Sessions
  dieses Accounts aus Sicherheitsgründen).

## Konto-Löschung (DSGVO: Recht auf Löschung)

```
DELETE /api/auth/me  { password?: string }
```

- Bei Accounts mit Passwort: Passwort-Reeingabe zur Bestätigung Pflicht.
  Bei Google-only-Accounts: einfacher Bestätigungs-Dialog im Frontend
  reicht (kein Passwort vorhanden).
- Löscht kaskadierend: `User`, alle zugehörigen `Client`s (via bestehendes
  `ondelete=CASCADE`), damit automatisch alle `Photo`s, `DayLog`s,
  `Pose`s, `AppSetting`s in der DB. Zusätzlich werden die physischen
  Bilddateien auf der Platte gelöscht (über die bestehenden
  `storage_paths`-Helfer aus Stufe 1 — der komplette
  `<client_id>/...`-Ordnerbaum jedes zugehörigen Clients).
- Frontend: Button im Account-Bereich mit "bist du sicher?"-Dialog, nach
  Erfolg Logout + Redirect zu `/login`.

## Datenexport (DSGVO: Recht auf Datenübertragbarkeit)

```
GET /api/auth/me/export
```

- Liefert ein JSON mit allen personenbezogenen Daten des Accounts:
  User-Stammdaten (ohne Passwort-Hash), alle Clients mit ihren Metriken,
  alle DayLogs, Liste der Foto-Dateipfade/-Metadaten (nicht die
  Bilddateien selbst — potenziell hunderte MB, echte Bilder exportiert man
  sich weiterhin direkt aus dem Dateisystem/der App).

## Rechts-Platzhalterseiten

`/datenschutz`, `/impressum`, `/agb` — statische Seiten mit Platzhaltertext
und deutlich sichtbarem Hinweis **"ENTWURF — vor echtem Live-Betrieb
rechtlich prüfen lassen"**. Verlinkt im Footer und in der
Signup-Consent-Checkbox. Der eigentliche Rechtstext (Datenschutzerklärung,
Impressum, AGB) wird bewusst NICHT von dieser Umsetzung verfasst — das
erfordert echte rechtliche Prüfung, bevor die App wirklich öffentlich
läuft (passt zeitlich zu Stufe 3).

Ebenfalls bewusst nicht Teil des Codes: Auftragsverarbeitungsverträge
(AVV) mit Resend und Google — das ist ein Vertrag zwischen dem
Betreiber (dir) und den Anbietern, kein Software-Feature.

## Rate-Limiting

Einfaches In-Memory-Rate-Limiting pro IP-Adresse (Sliding-Window-Zähler in
einem Prozess-internen `dict`, kein Redis nötig für den aktuellen
Single-Process-Betrieb) auf missbrauchsanfälligen Endpunkten:

- `POST /api/auth/signup` — 5 / Stunde / IP
- `POST /api/auth/forgot-password` — 5 / Stunde / IP
- `POST /api/auth/resend-verification` — 5 / Stunde / IP
- `POST /api/auth/login` — 10 / Stunde / IP

Umsetzung als FastAPI-Dependency. **Offener Punkt für Stufe 3**: bei
Wechsel auf Mehrprozess-/Mehrserver-Hosting muss das auf einen gemeinsamen
Store (Redis) wechseln — In-Memory funktioniert nur pro Einzelprozess.

## E-Mail-Versand (Resend)

- `RESEND_API_KEY` als neues Setting (`.env`, wie `GEMINI_API_KEY`).
- **Sandbox-Modus jetzt** — keine eigene Domain vorhanden, Mails gehen nur
  an die eigene, bei Resend verifizierte Test-Adresse. Echte
  Domain-Verifizierung für Versand an beliebige Nutzer ist ein **offener
  Punkt für Stufe 3** (sobald eine Domain existiert).
- Zwei einfache HTML-Mail-Templates: Bestätigungsmail, Passwort-Reset-Mail.
  Schlichtes, zur restlichen App passendes Layout — kein aufwendiges
  Design nötig.
- Versand läuft synchron im Request (kein Background-Queue-System bei
  diesem Umfang nötig) — bei einem Resend-Fehler bekommt der Nutzer eine
  ehrliche Fehlermeldung statt eines stillen Fehlschlags.

## Frontend-Änderungen

- **Login-Seite**: "Registrieren"-Link, "Mit Google anmelden"-Button
  (leitet auf `/api/auth/google/login`), Hinweis+Resend-Button bei 403
  wegen fehlender Verifizierung.
- **Neue Seite `/signup`**: E-Mail, Passwort, Passwort wiederholen, Name,
  Datenschutz-Consent-Checkbox (Pflicht). Nach Absenden: "Bitte E-Mail
  bestätigen"-Hinweisseite (kein Auto-Login wegen hartem Gate).
- **Neue Seite `/verify-email`**: verarbeitet Link-Klick, zeigt
  Erfolg/Fehler + Login-Link.
- **Neue Seiten `/forgot-password`** (E-Mail eingeben) und
  **`/reset-password?token=...`** (neues Passwort setzen).
- **Account-Bereich**: "Konto löschen"-Button (mit Bestätigungs-Dialog),
  "Meine Daten exportieren"-Button (lädt JSON herunter).
- **Neue Seiten `/datenschutz`, `/impressum`, `/agb`** (Platzhaltertext).
- Bestehende `Login.tsx` wird um die neuen Elemente ergänzt, keine
  grundlegende Neustrukturierung nötig.

## API-Design (Übersicht)

```
POST   /api/auth/signup
GET    /api/auth/verify-email
POST   /api/auth/resend-verification
GET    /api/auth/google/login
GET    /api/auth/google/callback
POST   /api/auth/forgot-password
POST   /api/auth/reset-password
DELETE /api/auth/me
GET    /api/auth/me/export
```

(bestehende `/api/auth/login`, `/logout`, `/me`, `/switch-to-coach` aus
Stufe 1 bleiben unverändert, `login` bekommt zusätzlich die
Verifizierungs-Prüfung)

## Ausdrücklich nicht Teil dieser Umsetzung

- Weitere OAuth-Provider (Apple, Microsoft, etc.) — nur Google
- Domain-Verifizierung bei Resend für echten Mailversand an beliebige
  Adressen (→ Stufe 3)
- Verteiltes Rate-Limiting (Redis) für Mehrprozess-Betrieb (→ Stufe 3)
- 2FA/MFA
- Rechtsverbindlicher Datenschutz-/Impressum-/AGB-Text (nur Platzhalter,
  echte rechtliche Prüfung folgt separat vor Live-Betrieb)
- Auftragsverarbeitungsverträge mit Resend/Google (Vertragssache, kein
  Code)
- Admin-UI zur Nutzerverwaltung
- Rollen/Rechte für Athleten-Logins (weiterhin nur Accounts selbst,
  `single`/`coach` — unverändert aus Stufe 1)
- Export der tatsächlichen Bilddateien im Datenexport (nur Metadaten/Pfade)
