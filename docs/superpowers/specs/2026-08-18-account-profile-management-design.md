# Account-Profil-Verwaltung (Stufe 6a) — Design-Spec

**Datum:** 2026-08-18
**Status:** Genehmigt

## Kontext

Die Account-Seite (`Account.tsx`) zeigt bisher Billing, KI-Einstellungen, Anzeige-Einstellungen und die Danger Zone, aber keinerlei Profil-Informationen. Der Nutzer kann seine eigene E-Mail-Adresse nirgends einsehen, sie nicht ändern, und sein Passwort nicht ändern (nur zurücksetzen über den unauthentifizierten Forgot-Password-Flow).

## Ziel

Ein neuer Profil-Bereich oben auf der Account-Seite: ein kleiner "Header" mit aktueller E-Mail und Mitglied-seit-Datum, plus - abhängig vom Account-Typ - die Möglichkeit, Passwort und/oder E-Mail zu ändern.

## Datenmodell

**`backend/app/schemas/auth.py` `UserOut`:**
- Neues Feld `created_at: datetime` (Spalte existiert bereits auf `User`, war bisher nicht Teil der API-Antwort).
- Neues `@computed_field` `has_google_account: bool` (analog zu `has_password`) - liest `google_id` (als `exclude=True`-Feld ins Schema aufgenommen, genau wie `password_hash`).

**`backend/app/models/email_token.py`:**
- Neuer Enum-Wert `EmailTokenPurpose.CHANGE_EMAIL`.
- Neue nullable Spalte `new_email: Mapped[str | None]` - trägt die angefragte neue Adresse, bis der Bestätigungslink geklickt wird. Nur für `CHANGE_EMAIL`-Tokens gesetzt, sonst `None`.
- Migration: sowohl lightweight SQLite-System (`_PENDING_COLUMNS`) als auch echte Alembic-Migration (Lehre aus dem `onboarding_completed_at`-Vorfall - siehe [[future-admin-dashboard]] Kontext) - **beide** Pfade müssen bedient werden.

## Backend-Endpunkte (alle in `backend/app/routers/auth.py`)

### `POST /api/auth/change-password`
- Body: `{current_password: str, new_password: str}`.
- Prüft `current_password` gegen den Hash des eingeloggten Nutzers (`get_current_user`-Dependency, kein Passwort-Feld nötig). 401/400 bei falschem aktuellem Passwort.
- Nutzt dieselbe Passwort-Stärke-Validierung wie `SignupRequest`/`ResetPasswordRequest` (Pydantic-Validator wiederverwenden, nicht duplizieren).
- Bei Erfolg: neuen Hash speichern, `204 No Content`. Kein Re-Login nötig, Session bleibt gültig (userid-basiert).
- Falls `current_user.password_hash is None` (Google-only-Account): `400` - "no password set on this account" (Frontend zeigt diesen Bereich aber ohnehin nicht an, das ist nur die Server-seitige Absicherung).
- Rate-Limit: eigener `RateLimiter` analog `login_rate_limit` (5/Stunde), gegen Brute-Force auf `current_password`.

### `POST /api/auth/change-email`
- Body: `{new_email: str, current_password: str}`.
- Prüft `current_password`. 401 bei falschem Passwort. `400` falls `current_user.password_hash is None` (Google-only - Server-seitige Absicherung, Frontend blendet das aus).
- Prüft `new_email` nicht bereits von einem ANDEREN Account genutzt (`db.query(User).filter(User.email == new_email, User.id != current_user.id)`) - `409` falls belegt.
- Invalidiert vorherige offene `CHANGE_EMAIL`-Tokens desselben Nutzers (`used_at = now()` setzen, damit nur der neueste Link gültig ist).
- Erzeugt neuen `EmailToken` (`purpose=CHANGE_EMAIL`, `new_email=new_email`, `expires_at = now + 24h`), verschickt Bestätigungslink an die **neue** Adresse (`send_verification_email`-Vorlage wiederverwendet/umformuliert - Linkziel ist der neue Bestätigungs-Endpunkt, nicht `verify-email`).
- `204 No Content`. Die E-Mail des Nutzers ändert sich hier noch NICHT.
- Rate-Limit: eigener `RateLimiter` (5/Stunde).

### `GET /api/auth/confirm-email-change?token=...`
- Analog zu `verify_email`: Signatur/Ablauf prüfen (`max_age_seconds = 60*60*24`), passenden `EmailToken`-Datensatz mit `purpose=CHANGE_EMAIL`, `used_at IS NULL` suchen.
- Bei Erfolg: `user.email = token_row.new_email`, `token_row.used_at = now()`, commit.
- **Kein Login-Zwang** - der Endpunkt braucht keine Session (Nutzer könnte den Link auf einem anderen Gerät/Browser öffnen als dem, auf dem er die Änderung angestoßen hat). Antwort: `{"changed": true, "new_email": "..."}`.
- Bei ungültigem/abgelaufenem Token: `400` mit verständlicher Fehlermeldung.
- Kein eigenes Rate-Limit nötig (Token selbst ist bereits der Schutz, analog `verify-email`).

## Frontend

### `frontend/src/api/client.ts`
- `api.auth.changePassword(currentPassword, newPassword)`.
- `api.auth.changeEmail(newEmail, currentPassword)`.
- `UserOut`-Type um `created_at: string` und `has_google_account: boolean` ergänzen.

### `frontend/src/pages/Account.tsx`
Neue `ProfileSection`-Komponente, direkt unter `PageHeader`, vor `BillingSection`:

- **Header-Zeile:** E-Mail-Adresse (`user.email`, groß/betont) + "Member since {created_at formatiert, z.B. 'Aug 2026'}" (kleiner, gedämpft) - in einer `Card`, kein eigenes Formular, nur Anzeige.
- **Passwort ändern** (eigene `Card`, nur wenn `user.has_password`): drei Felder (aktuelles Passwort, neues Passwort, neues Passwort wiederholen) - Client-seitiger Abgleich der beiden neuen Felder vor Submit, Server-Fehler (falsches aktuelles Passwort) als Inline-Fehlertext. Bei Erfolg: Felder leeren, kurze Erfolgsmeldung ("Password changed").
- **E-Mail ändern** (eigene `Card`, nur wenn `!user.has_google_account`): zwei Felder (neue E-Mail, aktuelles Passwort). Bei Erfolg: Formular durch Hinweistext ersetzen ("Check your inbox at {new_email} to confirm the change") - die angezeigte E-Mail in der Header-Zeile bleibt bewusst die ALTE, bis der Link geklickt und `/api/auth/me` neu geladen wurde (kein optimistisches Update, da die Änderung noch nicht wirksam ist).
- Analog zu `DangerZoneSection` prüft `user.has_password` NICHT `account_type` - ein Coach ohne Passwort (Google-only) sieht ebenfalls keinen Passwort-Bereich.

### Neue Route + Seite: E-Mail-Bestätigung
- Neue Seite `frontend/src/pages/ConfirmEmailChange.tsx`, Route `/confirm-email-change` (öffentlich, außerhalb `RequireAuth` - analog `/verify-email`).
- Liest `?token=` aus der URL, ruft beim Mount `api.auth.confirmEmailChange(token)` auf, zeigt Erfolg ("Email updated to ... - you can now log in with it.") oder Fehler ("Link is invalid or expired.") mit Link zurück zu `/login`.
- Falls der Nutzer noch eingeloggt ist (Session-Cookie vorhanden): kein Zwang zum Neu-Login, `/api/auth/me` wird beim nächsten Seitenwechsel ohnehin neu geladen und zeigt die neue Adresse.

## Out of Scope

- Kein "E-Mail-Änderung rückgängig machen"-Mechanismus.
- Keine Benachrichtigung an die ALTE Adresse über die Änderung (nur Bestätigung an die neue - YAGNI für jetzt, ließe sich später ergänzen).
- Kein erstmaliges Passwort-Setzen für Google-only-Accounts (bewusst laut Klärung ausgeschlossen).
- Keine 2FA/MFA.

## Testing-Ansatz

- Backend: Unit-Tests für alle drei neuen Endpunkte (`change-password`: falsches/richtiges aktuelles Passwort, schwaches neues Passwort, Google-only-Account-Fall; `change-email`: falsches Passwort, bereits vergebene Adresse, Erfolgsfall inkl. Token-Erzeugung; `confirm-email-change`: gültiger/abgelaufener/schon-benutzter Token, tatsächliche E-Mail-Änderung in der DB).
- Frontend: `npx tsc --noEmit`; manuelle Durchsicht (Google-Account sieht weder Passwort- noch E-Mail-Bereich, Passwort-Account sieht beide, E-Mail-Änderung zeigt korrekten Hinweistext, Bestätigungsseite funktioniert mit gültigem/ungültigem Token).
