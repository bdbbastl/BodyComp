# Design-Spec: Produktions-Hosting (Stufe 3)

## Kontext

BodyComp Tracker läuft bisher ausschließlich lokal: SQLite-Datei,
Fotos im lokalen Dateisystem, zwei getrennte Dev-Server (Vite :5173,
FastAPI :8000). Diese Runde bringt die App auf eine echte, für
mehrere Nutzer erreichbare Produktionsumgebung — als Voraussetzung
für Stufe 4 (Payment/Billing), die ohne echtes Hosting keinen Sinn
ergibt.

Bewusste Entscheidung aus der Klärungsrunde: Start mit einer **leeren**
Produktions-Datenbank — die lokale Entwicklungsumgebung wurde bereits
zuvor bewusst auf einen sauberen Stand zurückgesetzt, genau in
Vorbereitung hierauf. Kein Altdaten-Migrationsscript nötig.

## Architektur-Überblick

**Ein einziger Railway-Service** (FastAPI) liefert sowohl die API
(`/api/*`) als auch das gebaute Frontend (`npm run build`-Ergebnis,
statischer Fallback für alle anderen Pfade) aus — kein separates
Frontend-Hosting, keine CORS-Konfiguration zwischen zwei Domains nötig.
Dazu eine von Railway verwaltete **Postgres**-Instanz.

**Deploy-Trigger:** `main` wird die Produktions-Branch. Railway ist so
konfiguriert, dass jeder Push auf `main` automatisch ein neues
Deployment auslöst. Am bestehenden Workflow (Arbeit auf `dev`, `main`
bleibt bis zum bewussten Merge unangetastet) ändert sich nichts —
`main` bekommt nur jetzt zum ersten Mal eine echte Funktion als
Go-Live-Signal.

**Testing als Deploy-Gate:** Railways Build-Prozess (Nixpacks) führt
`pytest` (Backend) und `npx tsc --noEmit` (Frontend) als Teil des
Build-Schritts aus, bevor der Server startet. Schlägt einer der beiden
fehl, bricht der Build ab — kein zusätzliches CI-Tool nötig, Railway
selbst ist das Gate.

## Datenbank: SQLite → Postgres

- `settings.database_url` liest ab jetzt primär aus der Umgebungsvariable
  `DATABASE_URL` (die Railway automatisch setzt, sobald eine
  Postgres-Instanz verbunden ist); ohne gesetzte Variable bleibt der
  bisherige SQLite-Pfad als Fallback für die lokale Entwicklung
  bestehen — am lokalen Dev-Workflow ändert sich nichts.
- **Migrationen:** Umstieg von der bisherigen `run_lightweight_migrations`
  (rohe, SQLite-spezifische `ALTER TABLE`-Statements ohne Versionierung)
  auf echtes **Alembic** (bereits Dependency, bisher ungenutzt) — aber
  NUR für Postgres/Produktion. Da wir mit einer leeren DB starten,
  reicht EINE zusammengefasste "initial schema"-Migration, die den
  kompletten aktuellen Modellstand abbildet — kein Nachbau der
  historischen Zwischenschritte nötig.
- Lokale SQLite-Entwicklung bleibt unverändert beim bisherigen
  `Base.metadata.create_all` + Lightweight-Migrations-System — ein
  Alembic-Nachbau für SQLite lohnt sich nicht, da dort ohnehin jederzeit
  eine frische DB angelegt werden kann.
- `fix_users_password_hash_nullable.py` (einmalige Legacy-Fix-Migration
  aus Stufe 2) entfällt für Produktion vollständig — die dort behobene
  fehlerhafte Alt-Spalten-Definition hat in einer frischen Produktions-DB
  nie existiert.
- `PRAGMA foreign_keys=ON`-Listener in `core/database.py` wird auf "nur
  registrieren, wenn der SQLAlchemy-Dialekt SQLite ist" umgestellt —
  Postgres erzwingt Foreign-Keys ohnehin immer, der Listener wäre dort
  wirkungslos, aber besser explizit dialekt-bedingt als stillschweigend
  falsch angewendet.
- Alembic-Migrationen laufen automatisch als Teil des Railway-Start-
  Kommandos (`alembic upgrade head && uvicorn ...`), bevor der Server
  Traffic annimmt.

## Datei-Speicherung: lokales Filesystem → Cloudflare R2

**`StorageBackend`-Abstraktion:** `services/storage_paths.py` (bisher
reine Pfad-Konstruktion) wird zu einer echten Schnittstelle mit zwei
Implementierungen:

- `LocalFilesystemStorage` — heutiges Verhalten 1:1, für lokale
  Entwicklung.
- `R2Storage` — S3-kompatible API (via `boto3`, neue Dependency) gegen
  Cloudflare R2.

Eine Umgebungsvariable entscheidet, welches Backend aktiv ist (lokal:
Filesystem, Produktion: R2). Router/Services rufen nur noch
`storage.save(...)` / `storage.url_for(...)` / `storage.delete(...)`
auf, ohne das konkrete Backend zu kennen.

**Bildauslieferung:** Die bisherige `/media`-Route (FastAPI
`StaticFiles`) entfällt in Produktion — `PhotoOut`/`CheckinSubmissionOut`
liefern stattdessen **presigned URLs** (zeitlich befristete, direkt von
R2 signierte Links), die der Browser direkt gegen R2 lädt, nicht über
den FastAPI-Server. Schneller (R2s eigenes CDN) und server-schonender
(kein Datei-Streaming-Traffic auf dem App-Server).

**MediaPipe-Verarbeitung:** Die bestehende Bildverarbeitung
(`pose_normalization.py`, `thumbnails.py`, `heic.py`) bleibt inhaltlich
unverändert — sie bekommt über die `StorageBackend`-Abstraktion eine
lokale Temp-Datei geliefert (bei `R2Storage`: kurz herunterladen →
verarbeiten → Ergebnis hochladen; bei `LocalFilesystemStorage`: direkter
Pfad, kein Umweg). Kein Umbau der eigentlichen Bildverarbeitungs-Logik.

**Kompression beim Upload:** `sync_incoming_folder`
(`services/folder_sync.py`) ist bereits die EINE zentrale Stelle, durch
die jedes Foto läuft — Coach-Upload, Server-Ordner-Drop und
Klienten-Einreichung über den Magic-Link laufen alle durch diese
Funktion. Dort wird vor dem Speichern des Originals eine
Größen-/Qualitäts-Normalisierung ergänzt: mit Pillow (bereits
Dependency) Herunterskalieren auf eine maximale lange Kante von 2500px
(nur verkleinern, nie vergrößern) und Neukodierung als JPEG mit
Qualität 85, bevor die Datei als `original_path` gespeichert wird. Als
Nebeneffekt wird dabei die EXIF-Rotation permanent eingebrannt (heute
nur für Thumbnails korrigiert). Handy-Fotos (oft 8–15 MB) schrumpfen so
typischerweise auf wenige hundert KB, ohne dass MediaPipes
Posenerkennung oder die Timeline-Darstellung sichtbar leiden.

## Production-Basics

- **Backups:** Railways verwaltete Postgres-Instanz bekommt automatische
  tägliche Backups aktiviert (reines Plattform-Feature, kein eigener
  Code).
- **Error-Tracking:** Sentry SDK im Backend (FastAPI-Integration, fängt
  unbehandelte Exceptions automatisch ein) und im Frontend (React-
  Error-Boundary + Sentry-Browser-SDK) — ein gemeinsames Sentry-Projekt
  für Backend- und Frontend-Fehler an einer Stelle.
- **Uptime-Monitoring:** Ein externer, kostenloser Dienst (z.B.
  UptimeRobot) pingt periodisch `GET /api/health` und schickt eine
  E-Mail bei Nichterreichbarkeit — reine Drittanbieter-Konfiguration,
  kein eigener Code.

## Konfiguration / Secrets

Alle bisherigen `.env`-Werte (Google OAuth, Resend, Gemini,
Session-Secret) plus die neuen (R2-Zugangsdaten, `DATABASE_URL`,
Sentry-DSN) werden 1:1 in Railways Environment-Variablen-UI eingetragen
— Railway injiziert sie zur Laufzeit, analog zur heutigen `.env`-Datei.
`frontend_base_url` zeigt in Produktion auf die Railway-Subdomain der
App selbst (kein separates Frontend-Hosting mehr, siehe oben).

## Ausdrücklich nicht Teil dieser Umsetzung

- Kein eigener Domain-Anschluss — Plattform-Subdomain reicht zum Start,
  SSL automatisch inklusive, eigene Domain jederzeit später nachrüstbar.
- Kein Altdaten-Migrationsscript — leerer Start.
- Kein CDN vor dem Frontend — Railway/Nixpacks-Auslieferung reicht für
  die aktuelle Nutzerzahl.
- Kein Multi-Region- oder Hochverfügbarkeits-Setup.
- Keine Staging-Umgebung — nur Produktion (`main`), `dev` bleibt der
  lokale Arbeitsstand.
- Kein Payment/Billing (das ist Stufe 4, eigene Runde nach Abschluss
  dieser Spec).
