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
