# BodyComp Tracker (POC)

Lokal gehostete Web-App zur Verfolgung von Bodybuilding-Fortschritten anhand von Fotos.

## Struktur

```
backend/            FastAPI + SQLAlchemy + SQLite
  app/
    core/            Config, DB-Setup, Seed-Daten
    models/          SQLAlchemy-ORM-Modelle (Pose, DayLog, Photo)
    schemas/         Pydantic-Schemas (Request/Response)
    routers/         REST-Endpunkte
    services/        Fachlogik (EXIF, Ordner-Sync, MediaPipe-Normalisierung)
  data/
    photos_incoming/     Beobachteter Ordner für neue Fotos
    photos_processed/    Zugeordnete Originale, sortiert nach Datum
    photos_normalized/   MediaPipe-normalisierte Overlay-Versionen
  requirements.txt

frontend/            React + Vite + Tailwind CSS
  src/
    api/             Backend-Client
    components/      Wiederverwendbare UI-Bausteine
    pages/           Timeline, Unprocessed, Compare, Settings
    types/           Geteilte TS-Typen
```

## Backend starten

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API läuft auf `http://localhost:8000`, Swagger-UI unter `/docs`.

## Frontend starten

```bash
cd frontend
npm install
npm run dev
```

Läuft auf `http://localhost:5173`, proxyt `/api` und `/media` zum Backend.

## Cloud-Readiness (später)

- `app/core/config.py` kapselt alle Pfade/DB-URL über `Settings` (env-basiert) –
  ein S3/Postgres-Backend kann später als alternative Implementierung
  eingehängt werden, ohne Router/Services anzufassen.
- `services/` enthält reine Fachlogik ohne Framework-Kopplung – leicht
  in Background-Jobs/Queues (Cloud) auslagerbar.

## Produktions-Deployment (Stufe 3)

### Einmaliges Setup

1. **Railway-Projekt anlegen**, GitHub-Repo verbinden (Railway-GitHub-App
   braucht Zugriff auf private Repos - unter GitHub → Settings →
   Applications → Railway → Repository access prüfen/erweitern, falls
   das Repo dafür public gestellt werden musste).
2. **Postgres-Plugin** im Railway-Projekt hinzufügen - setzt `DATABASE_URL`
   automatisch als Umgebungsvariable für den App-Service.
3. **Tägliche Backups** für die Postgres-Instanz in den Railway-Plugin-
   Einstellungen aktivieren.
4. **Cloudflare R2 Bucket** anlegen (Name muss zu `R2_BUCKET` unten passen),
   API-Token mit Read/Write-Berechtigung erzeugen.
5. Folgende **Umgebungsvariablen** in Railway setzen (App-Service, nicht
   das Postgres-Plugin):
   - `BODYCOMP_SESSION_SECRET_KEY` (langer, zufälliger String)
   - `BODYCOMP_GOOGLE_CLIENT_ID`, `BODYCOMP_GOOGLE_CLIENT_SECRET`,
     `BODYCOMP_GOOGLE_REDIRECT_URI` (auf die Railway-Domain anpassen)
   - `BODYCOMP_RESEND_API_KEY`, `BODYCOMP_EMAIL_FROM_ADDRESS`
   - `BODYCOMP_FRONTEND_BASE_URL` (die Railway-App-URL selbst)
   - `GEMINI_API_KEY`
   - `BODYCOMP_STORAGE_BACKEND=r2`
   - `BODYCOMP_R2_ACCOUNT_ID`, `BODYCOMP_R2_ACCESS_KEY_ID`,
     `BODYCOMP_R2_SECRET_ACCESS_KEY`, `BODYCOMP_R2_BUCKET`
   - `BODYCOMP_SENTRY_DSN` (Backend-Fehler-Tracking)
   - `VITE_SENTRY_DSN` (Frontend-Fehler-Tracking, MUSS als Build-Zeit-
     Variable gesetzt sein, nicht nur zur Laufzeit - Vite bettet sie beim
     `npm run build` fest in den JS-Bundle ein)
6. **Uptime-Monitoring** einrichten: bei einem Dienst wie UptimeRobot
   (kostenlos) einen HTTP-Monitor auf `https://<deine-railway-domain>/api/health`
   anlegen, Intervall z.B. 5 Minuten, E-Mail-Alarm bei Ausfall.

### Laufender Betrieb

Jeder Push auf `main` (z.B. per `git merge dev` gefolgt von `git push`)
löst automatisch ein neues Deployment aus. Der Build bricht ab (kein
Deploy passiert), wenn Backend-Tests oder der Frontend-Typecheck fehlschlagen.

## Stripe-Setup (Stufe 4)

### Einmaliges Setup

1. **Produkte + Preise in Stripe anlegen** (Dashboard → Product
   catalog): je ein monatliches Abo für Starter/Pro/Business (Coach-
   Staffeln nach Klientenzahl) und Single (Einzelperson) - die
   jeweilige Price-ID (`price_...`) brauchst du für die Env-Vars unten.
2. **Webhook einrichten** (Dashboard → Developers → Webhooks → "+ Add
   endpoint"): Ziel-URL `https://DEINE-DOMAIN/api/billing/webhook`,
   Events: `customer.subscription.created`,
   `customer.subscription.updated`, `customer.subscription.deleted`.
   Nach dem Anlegen zeigt Stripe ein "Signing secret" (`whsec_...`) -
   das ist `BODYCOMP_STRIPE_WEBHOOK_SECRET` unten.
   **Wichtig:** Zusätzlich zu den obigen 3 Events muss am Webhook-
   Endpoint auch `customer.subscription.trial_will_end` abonniert
   werden (Dashboard → Developers → Webhooks → Endpoint → Events
   bearbeiten). Das ist ein manueller Schritt, der sowohl im Test- als
   auch im Live-Modus und für beide Railway-Environments (Staging +
   Production) jeweils getrennt konfiguriert werden muss.
3. Folgende zusätzliche **Umgebungsvariablen** in Railway setzen:
   - `BODYCOMP_STRIPE_SECRET_KEY` (`sk_test_...` zum Testen,
     `sk_live_...` für echten Betrieb)
   - `BODYCOMP_STRIPE_PUBLISHABLE_KEY`
   - `BODYCOMP_STRIPE_WEBHOOK_SECRET`
   - `BODYCOMP_STRIPE_PRICE_STARTER`, `BODYCOMP_STRIPE_PRICE_PRO`,
     `BODYCOMP_STRIPE_PRICE_BUSINESS`, `BODYCOMP_STRIPE_PRICE_SINGLE`
     (jeweils die `price_...`-ID aus Schritt 1)
4. **Customer Portal aktivieren** (Dashboard → Settings → Billing →
   Customer portal) - ohne diese einmalige Aktivierung schlägt der
   "Abo verwalten"-Link mit einem Stripe-Fehler fehl.

### Test- vs. Live-Modus

Stripe trennt Test- und Live-Daten komplett (eigene Produkte, eigene
Keys, eigener Webhook) - der Umschalter dafür sitzt oben rechts im
Stripe-Dashboard. Zum Entwickeln/Testen ausschließlich `sk_test_...`/
`pk_test_...`-Keys und im Test-Modus angelegte Price-IDs verwenden -
erst nach vollständigem Test-Durchlauf auf `sk_live_...`/`pk_live_...`
umschalten.
