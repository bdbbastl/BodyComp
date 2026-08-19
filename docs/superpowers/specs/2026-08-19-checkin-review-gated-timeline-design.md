# Check-in: Client-Pose-Zuordnung + Review-gesteuerte Timeline (Stufe 8) — Design-Spec

**Datum:** 2026-08-19
**Status:** Genehmigt

## Kontext

Heute landen per Magic-Link eingereichte Check-in-Fotos als `UNPROCESSED` in der Import-Queue des Coaches - der Coach muss sie manuell einer Pose zuordnen, bevor sie in Timeline/Compare erscheinen. Das führt zu zwei Problemen: (1) unnötiger manueller Aufwand für den Coach, (2) verwirrende Trennung zwischen "Check-in als gesehen markiert" (im Checkins-Tab) und "Fotos einer Pose zugeordnet" (im separaten Import-Tab) - Nutzer haben das erste mit dem zweiten verwechselt und sich gewundert, warum Fotos nicht in der Timeline auftauchen.

## Ziel

1. Der Klient wählt beim Einreichen selbst die Pose für jedes Foto (reduziert Coach-Aufwand).
2. Fotos werden sofort vollständig verarbeitet (verschoben, Thumbnail, KI-Normalisierung, Pose gesetzt) - dieselbe parallelisierte Pipeline wie beim Bulk-Import.
3. Trotzdem erscheinen die Fotos NICHT in Timeline/Compare, bis der Coach den zugehörigen Check-in als "reviewed" markiert (bestehender Mechanismus, keine neue Aktion nötig) - EIN klarer Kontrollpunkt statt zwei verwirrender.
4. Die Magic-Link-Seite selbst wird breiter/nutzt den Platz besser (aktuell `max-w-md`, wirkt bei mehreren Fotos gestaucht).

## Backend

### `GET /api/public/checkin/{token}` (`backend/app/schemas/checkin.py`, `backend/app/routers/public_checkin.py`)

`PublicCheckinPageOut` bekommt ein neues Feld:

```python
class PublicPoseOut(BaseModel):
    id: int
    name: str

class PublicCheckinPageOut(BaseModel):
    client_name: str
    submissions: list[PublicCheckinSubmissionOut]
    poses: list[PublicPoseOut]
```

`get_checkin_page` lädt zusätzlich `db.query(Pose).filter(Pose.client_id == client_row.id).order_by(Pose.sort_order).all()` und gibt sie mit zurück (bewusst nur `id`/`name` - kein `sort_order`/`created_at` nötig für die öffentliche Seite, kleinere Angriffsfläche).

### `POST /api/public/checkin/{token}/submit`

Neuer Form-Parameter `pose_ids: list[int] = Form(default=[])` - ein Eintrag pro Datei, IN DERSELBEN REIHENFOLGE wie `files` (Frontend hängt beide Listen im selben Durchlauf an dieselbe `FormData` an, siehe unten).

Validierung VOR jeder DB-Schreibung (gleiches Prinzip wie die bestehende Datei-Validierung oben im Endpunkt):
- `len(pose_ids) != len(files)` → 400 "Each photo needs a pose selected".
- Jede `pose_id` muss zu einer tatsächlich existierenden `Pose` DIESES Klienten gehören (`db.query(Pose).filter(Pose.id.in_(pose_ids), Pose.client_id == client_row.id).count() == len(set(pose_ids))`) → sonst 400 "Invalid pose selected".

Verarbeitung: statt wie bisher nur die Rohdatei zu speichern und `sync_incoming_folder` aufzurufen (was die Fotos als `UNPROCESSED` anlegt), wird pro Datei SOFORT dieselbe Pipeline wie in `backend/app/routers/photos.py`s `assign_photos_bulk` genutzt:

1. Datei wie bisher nach `photos_incoming/<client_id>/` schreiben (Pfad-Sanitizing unverändert).
2. `sync_incoming_folder(db, client_row.id)` aufrufen wie bisher, um die `Photo`-Rows (mit EXIF-Datum, HEIC-Vorschau etc.) anzulegen - unverändert.
3. Für jede neu angelegte `Photo`-Row (per `written_paths` identifiziert, wie bisher) UND ihre zugehörige `pose_id` (per Index-Zuordnung zur ursprünglichen `files`-Liste): `_get_or_create_day_log` (für das EXIF-Datum des jeweiligen Fotos - nicht das Einreichungsdatum, das bleibt wie beim regulären Import pro Foto individuell) + `_process_photo_files` (parallel über `ThreadPoolExecutor`, `PHOTO_PROCESSING_MAX_WORKERS`, importiert aus `app.routers.photos`) + `_apply_processed_result`, exakt wie beim Bulk-Assign - der Endpunkt ruft diese bereits bestehenden Bausteine wieder, statt sie zu duplizieren.
4. `photo.checkin_submission_id = submission.id` wird wie bisher gesetzt.

Ergebnis: `Photo.status` ist direkt nach der Einreichung `PROCESSED` (oder `NORMALIZATION_FAILED` im MediaPipe-Fehlerfall, best effort wie überall sonst auch), `pose_id` ist gesetzt - der Coach muss im Import-Tab nichts mehr tun.

### Sichtbarkeits-Gate: `GET /clients/{client_id}/photos` (`backend/app/routers/photos.py`, Funktion `list_photos`)

Neuer Filter: ein Foto mit gesetztem `checkin_submission_id` wird NUR zurückgegeben, wenn die zugehörige `CheckinSubmission.status == REVIEWED` ist. Fotos ohne `checkin_submission_id` (normale Coach-Uploads) sind unverändert immer sichtbar (sobald `pose_id` gesetzt ist, wie bisher - dieser Endpunkt filtert generell nicht nach Status, das macht weiterhin das Frontend über `pose_id`-Präsenz).

```python
from app.models.checkin_submission import CheckinStatus, CheckinSubmission

q = db.query(Photo).filter(Photo.client_id == client_row.id)
q = q.outerjoin(CheckinSubmission, Photo.checkin_submission_id == CheckinSubmission.id).filter(
    (Photo.checkin_submission_id.is_(None)) | (CheckinSubmission.status == CheckinStatus.REVIEWED)
)
```

Betrifft sowohl Timeline (nutzt diesen Endpunkt ohne Pose-Filter) als auch Compare (nutzt ihn mit `pose_id`-Filter) - beide profitieren automatisch von derselben zentralen Filterung, keine Doppelimplementierung.

**Auslöser für die Sichtbarkeit:** der bereits bestehende `PATCH /clients/{client_id}/checkins/{checkin_id}` mit `{"mark_reviewed": true}` (unverändert, bereits genutzt im Checkins-Tab und im neuen Coach-Dashboard-Widget) - keine neue Aktion, kein neuer Endpunkt nötig. Sobald der Coach das setzt, tauchen die zugehörigen Fotos beim nächsten Query in Timeline/Compare auf.

## Frontend

### `frontend/src/pages/CheckinSubmit.tsx`

- Äußerer Container: `max-w-md` → `max-w-2xl` (mehr Platz für die Foto/Pose-Zuordnung).
- `PublicCheckinPage`-Typ (`frontend/src/types/index.ts`) bekommt `poses: { id: number; name: string }[]`.
- Neuer lokaler State: `const [photoPoses, setPhotoPoses] = useState<Record<number, number | "">>({})` (Index in `files` → gewählte `pose_id`, `""` = noch nicht gewählt).
- Sobald Dateien ausgewählt sind, wird statt der reinen Dateizahl-Anzeige eine Grid-Liste gerendert (`grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3`), pro Datei: `URL.createObjectURL(file)`-Vorschaubild (kleine Kachel) + darunter ein `<select>` mit den `poses`-Optionen (Platzhalter-Option "Choose pose…", leer/nicht wählbar als Startwert).
- "Submit check-in"-Button bleibt `disabled`, wenn (a) die Mutation läuft ODER (b) mindestens eine ausgewählte Datei noch keine Pose hat (`files.length > 0 && files.some((_, i) => !photoPoses[i])`).
- `api.publicCheckin.submit` bekommt einen neuen Parameter `poseIds: number[]` (parallel zu `files`, gleiche Reihenfolge/Länge) - im `FormData`-Aufbau werden `files` und `pose_ids` im selben Schleifendurchlauf angehängt, damit die Reihenfolge server-seitig sicher übereinstimmt.

### `frontend/src/api/client.ts`

`publicCheckin.submit`-Signatur erweitert um `pose_ids` im `FormData`-Aufbau (siehe oben) - `PublicCheckinPage`-Typ zeigt auf das neue `poses`-Feld aus `types/index.ts`.

## Out of Scope

- Keine automatische Pose-Vorschlagsfunktion für den Klienten (kein Reuse von `pose_suggestion.py` auf der öffentlichen Seite - YAGNI für v1, der Klient wählt manuell).
- Keine Änderung an der bestehenden Möglichkeit des Coaches, eine bereits gesetzte Pose nachträglich zu ändern (`PATCH /clients/{id}/photos/{id}/pose`, unverändert nutzbar - z.B. falls der Klient sich vertan hat).
- Keine Änderung an `ClientCheckins.tsx` (Checkins-Tab) selbst - "mark reviewed" existiert bereits und braucht keine UI-Änderung, nur die neue Backend-Konsequenz (Fotos werden dadurch sichtbar).
- Keine Migration bestehender, bereits eingereichter aber noch unverarbeiteter Check-in-Fotos (Altfälle bleiben im bisherigen `UNPROCESSED`-Zustand, laufen weiter über den bisherigen manuellen Import-Weg - kein Cutover-Skript, zu kleiner Nutzen für den Aufwand bei einer noch jungen App).

## Testing-Ansatz

- Backend: Test, dass eine Einreichung mit `pose_ids` die Fotos direkt `PROCESSED` mit korrektem `pose_id` anlegt. Test, dass `list_photos` Check-in-Fotos VOR `mark_reviewed` ausblendet und DANACH anzeigt. Test, dass normale (nicht Check-in-) Fotos vom neuen Filter unberührt bleiben. Test für die `pose_ids`-Validierung (falsche Länge, fremde/unbekannte Pose-ID).
- Frontend: `npx tsc --noEmit`; manuelle Durchsicht (Magic-Link-Seite zeigt Pose-Auswahl pro Foto, Submit bleibt gesperrt bis alle gewählt, Timeline zeigt die Fotos erst nach "mark reviewed" durch den Coach, Compare funktioniert dann ebenso).
