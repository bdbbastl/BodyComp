# Check-in: Foto-Datum manuell korrigieren — Design

## Ziel

Auf der Magic-Link-Check-in-Seite ([CheckinSubmit.tsx](../../../frontend/src/pages/CheckinSubmit.tsx)) wird das ermittelte Aufnahmedatum der ausgewählten Fotos (EXIF `DateTimeOriginal`, sonst Datei-mtime-Fallback — siehe `get_taken_at()` in [exif.py](../../../backend/app/services/exif.py)) bereits informativ im Header angezeigt. Ist das ermittelte Datum falsch (z.B. EXIF fehlt bei einem Screenshot/weitergeleiteten Foto und der mtime-Fallback greift, oder der Klient reicht ein älteres Foto nach), kann der Klient das aktuell nicht korrigieren. Diese Spec ergänzt eine Klick-zu-Bearbeiten-Möglichkeit: Klick auf das angezeigte Datum öffnet einen nativen Datums-Picker, die Auswahl überschreibt das Datum für alle Fotos dieser Einreichung.

## Umfang

- Nur der Fall **"alle ausgewählten Fotos haben dasselbe ermittelte Datum"** ist betroffen — bei "Mixed dates" bleibt das Label wie bisher rein informativ, nicht klickbar (kein Override-Mechanismus für den Mixed-Fall; seltener Rand-Fall, nicht Teil dieser Iteration).
- Die Korrektur gilt für **alle** Fotos der aktuellen Einreichung gemeinsam (kein Foto-für-Foto-Picker).
- Serverseitige Validierung: das gewählte Datum darf **nicht in der Zukunft** liegen (weder heute noch später ist "Zukunft" — heute ist erlaubt, alles danach nicht).

## Frontend

**Anzeige & Interaktion** ([CheckinSubmit.tsx](../../../frontend/src/pages/CheckinSubmit.tsx)):

- Neuer State `photoDateOverride: string | null` (ISO `YYYY-MM-DD`, `null` = kein Override, EXIF/mtime-Wert gilt). Reset auf `null` bei jeder neuen Dateiauswahl (analog zu `photoDates`).
- Das bestehende `photoDateLabel` (aktuell reiner Text) wird, wenn `photoDates` ein einheitliches Datum ergeben (nicht "Mixed dates", nicht leer), als klickbarer Button mit kleinem Stift-Icon gerendert. Bei "Mixed dates" bleibt es unverändertes `<p>`, nicht klickbar.
- Klick auf den Button blendet an derselben Stelle ein `<input type="date">` ein (autofokussiert — auf Mobile öffnet Fokussieren eines Date-Inputs direkt den nativen System-Picker). `max` = heutiges Datum (lokal, `YYYY-MM-DD`) — verhindert serverseitig ohnehin abgelehnte Zukunftsdaten schon in der Bedienung.
  - Vorbelegt mit dem Override-Wert falls vorhanden, sonst mit dem ermittelten EXIF-Datum (aus `photoDates[0]`, lokal zu `YYYY-MM-DD` formatiert).
- `onChange`/`onBlur` des Date-Inputs: Wert übernehmen, `photoDateOverride` setzen, zurück zur Label-Ansicht (jetzt mit dem korrigierten Datum, weiterhin mit Stift-Icon — bleibt klickbar für erneute Korrektur).
- Anzeige-Priorität für das Label: `photoDateOverride` falls gesetzt, sonst das ermittelte EXIF/mtime-Datum wie bisher.

**Submit** ([api/client.ts](../../../frontend/src/api/client.ts) `publicCheckin.submit`):

- Neues optionales Payload-Feld `photo_date?: string` (ISO `YYYY-MM-DD`). Wird nur gesetzt, wenn `photoDateOverride !== null`; als `photo_date` im `FormData` mitgeschickt. Ohne Override wird das Feld weggelassen (Backend verhält sich exakt wie bisher — reiner EXIF/mtime-Pfad, keine Verhaltensänderung für den unveränderten Fall).

## Backend

**Endpunkt** ([public_checkin.py](../../../backend/app/routers/public_checkin.py) `submit_checkin`):

- Neuer optionaler Parameter `photo_date: str | None = Form(default=None)`.
- Validierung direkt zu Beginn (vor jeder DB-Schreibung, analog zu den bestehenden Validierungen für `files`/`pose_ids`):
  - Parsen als ISO-Datum (`date.fromisoformat`) — bei Parse-Fehler `400 "Invalid date format"`.
  - Liegt das geparste Datum nach `date.today()` → `400 "Date cannot be in the future"`.
- Nach dem bestehenden Foto-Sync-Block (`sync_incoming_folder`, der `taken_at` normal aus EXIF/mtime setzt) und **vor** der Day-Log-Zuordnungs-Schleife: wenn `photo_date` gesetzt ist, wird `taken_at` für jedes `photo` aus `photos_to_process` auf `datetime.combine(parsed_photo_date, time.min)` überschrieben. Die anschließende Day-Log-Zuordnung (`day_date = photo.taken_at.date()`) liest danach automatisch den korrigierten Wert — kein separater Code-Pfad nötig, keine Divergenz zwischen `Photo.taken_at` und der Day-Log-Zuordnung.
- Wirkt nur auf **Fotos**, nicht auf die separate "heute"-DayLog-Zuordnung für Gewicht/Notiz (unverändert, siehe bestehender Kommentar in der Datei).

## Fehlerfälle

| Fall | Verhalten |
|---|---|
| Kein `photo_date` mitgeschickt | Unverändert: EXIF/mtime-Pfad wie bisher. |
| `photo_date` ungültiges Format | `400 Invalid date format` |
| `photo_date` in der Zukunft | `400 Date cannot be in the future` |
| `photo_date` gesetzt, aber `files` leer (nur Gewicht/Notiz-Check-in) | Keine Wirkung — es gibt keine Fotos zu überschreiben; kein Fehler (Feld wird einfach ignoriert). |

## Out of Scope

- Kein Per-Foto-Override bei "Mixed dates".
- Keine Änderung der Uhrzeit-Komponente außer dem Default `00:00:00` bei Override (Klient wählt nur ein Datum, keine Uhrzeit).
- Keine nachträgliche Korrektur bereits eingereichter Check-ins über diese Seite (nur beim aktuellen, noch nicht abgeschickten Formular).

## Tests

- Backend: neuer Test analog zum bestehenden EXIF-Regressionstest (`test_submit_checkin_uses_photo_exif_date_not_upload_date`) — mit `photo_date` im Request, erwartet `Photo.taken_at` und der zugehörige `DayLog` reflektieren das übergebene Datum, nicht das EXIF-Datum.
- Backend: Test für `400` bei Zukunftsdatum.
- Backend: Test für `400` bei ungültigem Format.
- Backend: Test, dass ohne `photo_date` weiterhin das EXIF-Datum greift (Rückwärtskompatibilität — vorhandener Test deckt das ab, hier nur sicherstellen, dass er weiterhin grün bleibt).
