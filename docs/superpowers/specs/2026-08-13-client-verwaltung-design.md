# Client-/Mandantenverwaltung — Design (Stufe 1)

**Datum:** 2026-08-13
**Status:** Zur Freigabe

## Kontext

BodyComp Tracker ist aktuell eine Single-User-App: eine Timeline, ein Foto-Bestand,
eine Pose-Liste, keine Trennung zwischen verschiedenen Personen. Ziel ist es,
Progress-Fotos für **mehrere Athleten** verwaltbar zu machen — ein Coach loggt
sich ein, sieht ein Dashboard mit seinen Kunden, legt neue an, und öffnet pro
Kunde das bestehende Verwaltungsinterface (Timeline/Import/Compare/Statistik/
Settings) exklusiv für dessen Daten.

## Größerer Kontext und bewusste Abgrenzung

Der Wunsch des Nutzers geht langfristig deutlich weiter: ein öffentlicher,
gehosteter Webservice mit Selbstregistrierung und Payment/Billing. Das wurde
bewusst in vier Stufen zerlegt, von denen **dieses Dokument ausschließlich
Stufe 1 spezifiziert**:

1. **Mandantenfähigkeit** (dieses Dokument) — Coach-Login, mehrere
   Athleten-Profile, Datentrennung. Läuft weiterhin lokal, keine öffentliche
   Registrierung.
2. **Public Auth** — Self-Signup, E-Mail-Verifizierung, Passwort-Reset,
   ggf. OAuth. *Eigene Spec, eigener Brainstorming-Durchlauf.*
3. **Produktions-Hosting** — SQLite → Postgres, lokales Filesystem →
   Object-Storage für Fotos (S3-kompatibel). *Eigene Spec.*
4. **Payment/Billing** — Stripe-Anbindung, Pläne/Limits, Abo-Verwaltung.
   *Eigene Spec.*

Diese Abgrenzung ist explizit: Stufe 1 baut das Fundament so, dass Stufe 2–4
sauber andocken können (siehe insbesondere Abschnitt "Dateiablage" zur
Kompatibilität mit künftigem Object-Storage), spezifiziert oder implementiert
sie aber nicht.

## Datenmodell

### Neu: `User` (der Coach)

| Feld | Typ | Hinweis |
|---|---|---|
| id | int, PK | |
| email | string, unique | Login-Kennung |
| password_hash | string | bcrypt |
| created_at | datetime | |

### Neu: `Client` (das Athleten-Profil)

| Feld | Typ | Hinweis |
|---|---|---|
| id | int, PK | |
| owner_id | int, FK → User | Cascade-Delete mit dem Coach |
| name | string | |
| height_cm | float, nullable | |
| age | int, nullable | |
| gender | string, nullable | Freitextfeld, kein festes Enum |
| start_date | date, nullable | |
| created_at | datetime | |

Die vier Metrik-Felder sind bewusst minimal gehalten ("... damit wir was haben,
das wir noch erweitern können") — spätere Ergänzungen (Zielgewicht, Notizen,
etc.) sind rein additive Migrationen.

### Bestehende Tabellen: `client_id` ergänzen

- **`Pose`** — `client_id` (FK → Client, `ondelete=CASCADE`) ergänzt. Die
  bisherige globale `UNIQUE(name)`-Constraint wird zu `UNIQUE(client_id, name)`.
  Jeder Kunde hat seine eigene, unabhängige Pose-Liste; beim Anlegen eines
  neuen Kunden werden die bisherigen 7 Standard-Posen als Vorlage kopiert
  (analog zum heutigen `seed_default_poses`, aber pro Kunde statt einmalig
  global).
- **`DayLog`** — `client_id` ergänzt. `UNIQUE(date)` wird zu
  `UNIQUE(client_id, date)`.
- **`Photo`** — `client_id` ergänzt. `original_path` bleibt technisch global
  eindeutig (der Pfad enthält ja den Kunden-Ordner, siehe unten), keine
  Änderung an der Constraint nötig.

### `AppSetting` wandert zum Coach

Der Gemini-API-Key und die Anzeige-Einstellungen (Timeline-Spaltenzahl,
Wochen/Seite) hängen künftig am `User` (Coach), nicht mehr global und nicht
pro Kunde — ein Coach hat einen Key/eine Bedienpräferenz für alle seine
Kunden. Dafür wird `AppSetting` um `owner_id` (FK → User) erweitert, bzw. die
bisherige Key-Value-Struktur bleibt, nur pro Coach statt global eindeutig.

## Authentifizierung

**Cookie-basiertes Session-Login**, kein Bearer-Token im Frontend-Code:

- `POST /api/auth/login` (E-Mail + Passwort) prüft gegen `password_hash`
  (bcrypt), setzt bei Erfolg ein signiertes, **httpOnly** Cookie.
- `POST /api/auth/logout` löscht das Cookie.
- Eine zentrale FastAPI-Dependency (`get_current_user`) liest das Cookie,
  validiert die Signatur und liefert den eingeloggten `User` — oder `401`.
- Kein Token-Handling im Frontend nötig (kein Storage, kein manuelles
  Anhängen an Requests) — der Browser übernimmt das automatisch bei
  Same-Origin-Requests.

Begründung gegen Bearer-Token (Alternative, für später nicht ausgeschlossen):
für eine reine Web-SPA ohne native Mobile-App ist httpOnly-Cookie sicherer im
Default (kein XSS-Zugriff auf die Session) und braucht keine
Frontend-seitige Token-Verwaltung. Der Wechsel auf Token-Auth bliebe bei
Bedarf in Stufe 2 möglich, ohne das Datenmodell anzufassen.

## API-Design

Alle bestehenden Endpunkte werden unter den Kunden gehängt:

```
POST   /api/auth/login
POST   /api/auth/logout

GET    /api/clients                       Liste (nur eigene Kunden)
POST   /api/clients                       Neuen Kunden anlegen
GET    /api/clients/{client_id}           Details
PATCH  /api/clients/{client_id}           Metriken bearbeiten

GET    /api/clients/{client_id}/photos
POST   /api/clients/{client_id}/photos/sync
POST   /api/clients/{client_id}/photos/upload
...    (alle bisherigen /api/photos/*-Routen analog)

GET    /api/clients/{client_id}/poses
...    (alle bisherigen /api/poses/*-Routen analog)

GET    /api/clients/{client_id}/day-logs
...

GET    /api/clients/{client_id}/comparisons
...

GET    /api/settings/gemini-key           unverändert, hängt am Coach
PUT    /api/settings/gemini-key
GET    /api/settings/display
PUT    /api/settings/display
```

Eine zentrale Dependency (`get_owned_client`) prüft bei **jedem**
`/clients/{client_id}/...`-Aufruf: (1) ist der Coach eingeloggt, (2) gehört
`client_id` zu genau diesem Coach. Trifft (2) nicht zu (fremder oder
nicht-existenter Kunde), liefert die API `404` — nicht `403` — damit sie
nicht einmal verrät, ob eine fremde Kunden-ID überhaupt existiert.

## Dateiablage

```
data/
  photos_incoming/<client_id>/<dateiname>
  photos_processed/<client_id>/<datum>/<dateiname>
  photos_normalized/<client_id>/<pose_id>/<photo_id>.jpg
```

Thumbnails (`*.thumb.jpg`) und HEIC-Previews (`*.preview.jpg`) liegen wie
bisher direkt neben ihrer Quelldatei. Der "Ordner synchronisieren"-Button und
der Datei-Upload arbeiten künftig nur noch im `photos_incoming`-Ordner des
gerade geöffneten Kunden — löst das bisherige Problem eines geteilten,
besitzerlosen Incoming-Ordners.

**Kompatibilität mit künftigem Object-Storage (Stufe 3, nicht Teil dieser
Umsetzung):** Die in der DB gespeicherten Pfade sind bereits relative Keys
(`<client_id>/<datum>/<dateiname>`), kein absoluter Systempfad — dieses
Format entspricht 1:1 einem S3-Objekt-Key. Es wird **keine**
Storage-Abstraktionsschicht gebaut (YAGNI für Stufe 1), aber die
Pfad-Konstruktion bleibt an der bestehenden zentralen Stelle
(`config.py`/`folder_sync.py`), damit der spätere Umstieg ein
Adapter-Austausch bleibt statt eines Umbaus.

## Frontend

- **`/login`** — E-Mail + Passwort, Redirect zum Dashboard bei Erfolg.
- **`/` (Dashboard)** — Liste/Kacheln aller eigenen Kunden, Button "Neuen
  Kunden anlegen" (Formular: Name, Größe, Alter, Geschlecht, Startdatum).
  Klick auf einen Kunden → `/clients/:id/timeline`.
- **Bestehende Seiten** (Timeline, Import, Compare, Statistik) wandern
  inhaltlich unverändert unter `/clients/:id/*`. Die Navigationsleiste zeigt
  zusätzlich den Namen des aktiven Kunden und einen Link zurück zum
  Dashboard.
- **Settings wird aufgeteilt:** Posen-Konfiguration bleibt kundenspezifisch
  unter `/clients/:id/settings`. Gemini-Key und Anzeige-Einstellungen
  wandern in einen neuen, kundenunabhängigen Bereich (z.B. `/account`), da
  sie am Coach hängen.
- **Logout** — Button in der Navigationsleiste, überall sichtbar.

## Migration des bestehenden Datenbestands

Einmaliges Migrationsscript, das beim ersten Start nach dem Umbau automatisch
läuft (Erkennungsmerkmal: noch kein `User` in der DB vorhanden):

1. Legt den Coach-Account an (`basti.auer@outlook.com`, Startpasswort wurde
   im Chat übergeben — **nicht** im Repo gespeichert, wird bei der
   Implementierung direkt gehasht in die DB geschrieben, taucht in keiner
   committeten Datei im Klartext auf).
2. Legt den Kunden **"Mein Profil"** an, diesem Coach zugeordnet.
3. Befüllt `client_id` auf allen bestehenden `Photo`-, `DayLog`- und
   `Pose`-Zeilen (aktuell: 175 Fotos, 27 Tage-Einträge, 7 Posen) mit der ID
   von "Mein Profil".
4. Verschiebt die zugehörigen Dateien in die neue Ordnerstruktur
   (`photos_processed/<mein-profil-id>/<datum>/...` usw.) und aktualisiert
   die in der DB gespeicherten Pfade entsprechend.
5. Übernimmt den aktuellen Gemini-Key aus der bestehenden `AppSetting`/`.env`
   in den neuen Coach-Account.

Bestehende Bilddateien und normalisierte Versionen bleiben inhaltlich
unangetastet — nur Pfade und Zuordnungen ändern sich.

## Ausdrücklich nicht Teil dieser Umsetzung

- Öffentliche Registrierung, E-Mail-Verifizierung, Passwort-Reset-per-Mail
  (→ Stufe 2)
- Wechsel auf Postgres oder Object-Storage (→ Stufe 3)
- Payment/Billing, Pläne, Limits (→ Stufe 4)
- Rollen/Rechte für Athleten-Logins (nur Coach-Login in Stufe 1)
- Eine UI zum Anlegen weiterer Coach-Accounts (passiert vorerst manuell,
  analog zum bestehenden Migrationsscript)

## Offene technische Fragen für die Umsetzungsplanung

Diese sind bewusst *nicht* Teil dieser Design-Entscheidung, sondern werden im
Implementierungsplan (`writing-plans`) konkretisiert:

- Genaue Session-Cookie-Bibliothek/-Implementierung (z.B. `itsdangerous`
  Signed Cookies vs. eine schlanke Session-Middleware)
- Exakte Migrations-Reihenfolge und Rollback-Strategie, falls die
  Dateiverschiebung mittendrin fehlschlägt
