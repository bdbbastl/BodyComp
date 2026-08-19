# Check-in Foto-Aufnahmedatum-Header — Design-Spec (Korrektur)

**Datum:** 2026-08-19
**Status:** Genehmigt

## Kontext

Der zuvor umgesetzte Datums-Header auf der Magic-Link Check-in-Seite (`frontend/src/pages/CheckinSubmit.tsx`) zeigte fälschlich das aktuelle Gerätedatum (`new Date()`), unabhängig von den ausgewählten Fotos, und war bereits vor jeder Dateiauswahl sichtbar. Die eigentliche Anforderung: das Aufnahmedatum DER AUSGEWÄHLTEN FOTOS (EXIF `DateTimeOriginal`) soll angezeigt werden, und zwar erst NACHDEM Fotos ausgewählt wurden.

## Ziel

Über dem Foto-Auswahlbereich der Magic-Link-Seite wird - sobald Dateien ausgewählt sind - das tatsächliche Aufnahmedatum dieser Fotos angezeigt (gleiche Formatierung wie Timeline, via `formatDateWithWeek`). Vor jeder Dateiauswahl wird kein Datum angezeigt.

## Umsetzung

### Neue Abhängigkeit: `exifr`

`frontend/package.json` bekommt `exifr` als neue Dependency - liest EXIF-Metadaten direkt aus `File`-Objekten im Browser, ohne Upload. Kleine, weit verbreitete Bibliothek, kein Backend-Äquivalent nötig (die eigentliche `taken_at`-Bestimmung beim Verarbeiten bleibt unverändert serverseitig in `backend/app/services/exif.py`).

### `frontend/src/pages/CheckinSubmit.tsx`

- Neuer State: `const [photoDates, setPhotoDates] = useState<(Date | null)[]>([])`.
- Im bestehenden `useEffect`, das aktuell die Preview-URLs aus `files` erzeugt (Abschnitt mit `URL.createObjectURL`), wird zusätzlich pro Datei asynchron `exifr.parse(file, ["DateTimeOriginal"])` aufgerufen:
  - EXIF-Tag `DateTimeOriginal` vorhanden → dieses Datum verwenden.
  - Kein EXIF-Tag (z.B. Screenshot, bereits bearbeitetes Bild) → Fallback auf `new Date(file.lastModified)`, analog zum Fallback-Verhalten der bestehenden Backend-Funktion `get_taken_at()` (EXIF zuerst, dann Datei-mtime).
  - Fehler beim Parsen (kaputte/nicht unterstützte Datei) → ebenfalls Fallback auf `file.lastModified`.
- Abgeleiteter Anzeige-Wert (kein zusätzlicher State, direkt aus `photoDates` berechnet):
  - `files.length === 0` → kein Header, nichts rendern.
  - Alle vorhandenen `photoDates`-Einträge liegen auf demselben Kalendertag (Datum ohne Uhrzeit vergleichen) → `formatDateWithWeek(...)` mit diesem Tag.
  - Unterschiedliche Kalendertage unter den Einträgen → Text "Mixed dates" statt eines Datums.
- `photoDates` wird wie `previewUrls`/`photoPoses` bei jeder neuen Dateiauswahl zurückgesetzt (leeres Array), damit keine veralteten Datumswerte von der vorherigen Auswahl übrig bleiben, während die neuen EXIF-Reads noch laufen (kurzzeitig kein Header sichtbar, bis die Reads durch sind - kein Blocker/Ladeanzeige nötig, EXIF-Parsing ist sehr schnell).
- Das ermittelte Datum wird NICHT ans Backend mitgeschickt und beeinflusst die Verarbeitung nicht - rein informative Anzeige. `api.publicCheckin.submit` bleibt unverändert.

## Out of Scope

- Kein Neuberechnen bei Datei-Reihenfolge-Änderung (Dateien sind nicht umsortierbar).
- Keine Anzeige eines Pro-Foto-Datums in der einzelnen Foto-Kachel (nur der eine gemeinsame Header über der ganzen Auswahl).
- Keine Änderung an der serverseitigen `taken_at`-Bestimmung (`backend/app/services/exif.py`) - die bleibt die einzige Quelle der Wahrheit für das tatsächlich gespeicherte Aufnahmedatum.

## Testing-Ansatz

- Frontend: `npx tsc --noEmit`. Manuell: Seite laden (kein Header sichtbar), ein Foto mit EXIF-Datum auswählen (Header zeigt korrektes Datum), mehrere Fotos vom selben Tag auswählen (ein Header), Fotos von unterschiedlichen Tagen auswählen ("Mixed dates"), ein Foto ohne EXIF (z.B. Screenshot) auswählen (Fallback auf Datei-Änderungsdatum, kein Crash).
