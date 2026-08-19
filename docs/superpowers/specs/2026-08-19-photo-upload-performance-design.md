# Foto-Upload/Speicher-Performance (Stufe 7a) — Design-Spec

**Datum:** 2026-08-19
**Status:** Genehmigt

## Kontext

"Fotos hochladen" und "Alle zugeordneten speichern" fühlen sich extrem langsam an (mehrere zehn Sekunden bei einem typischen Batch von ~8 Fotos). Root Cause: sowohl `POST /photos/upload` als auch `POST /photos/assign-bulk` verarbeiten alle Dateien eines Batches vollständig SEQUENZIELL, eine nach der anderen. Pro Foto in `assign-bulk` laufen dabei bis zu 4 synchrone Netzwerk-Roundtrips zu Cloudflare R2 (Original, HEIC-Vorschau, Thumbnail, normalisiertes Bild) PLUS eine CPU-intensive MediaPipe-Posenerkennung - alles hintereinander, nichts parallel.

## Ziel

Denselben Batch spürbar schneller verarbeiten (Zielgröße: 3-5 Sekunden für einen typischen ~8-Foto-Batch, abhängig von Server-CPU/Netzwerk), OHNE neue Fehlerquellen oder Inkonsistenz-Fenster einzuführen. Die Antwort wird weiterhin erst gesendet, wenn ALLES (lokale Datei, DB, R2) tatsächlich fertig und korrekt ist - explizit KEIN Hintergrund-/Fire-and-forget-Mechanismus für R2-Uploads.

## Architektur

Beide betroffenen Endpunkte bekommen dieselbe Grundidee: die pro-Datei/pro-Foto-Arbeit läuft über einen begrenzten Thread-Pool PARALLEL statt in einer `for`-Schleife SEQUENZIELL. Die Response wartet weiterhin auf `concurrent.futures.wait(...)`/`as_completed(...)`, bis alle Worker fertig sind - kein Unterschied im Erfolgs-/Fehlerverhalten aus Nutzersicht, nur in der Wanduhrzeit.

**Warum Thread-Pool statt echtem asyncio:** Die beteiligten Operationen (Datei-I/O, boto3-Netzwerkcalls, OpenCV/MediaPipe/Pillow-Bildverarbeitung) sind alle blockierend/synchron und geben in ihren nativen C-Aufrufen die GIL frei - ein `ThreadPoolExecutor` bringt hier echten Parallelitätsgewinn, ohne den bestehenden synchronen Code-Stil der Services (`storage_sync.py`, `pose_normalization.py`, `thumbnails.py`) umschreiben zu müssen. Ein voller asyncio-Umbau wäre unverhältnismäßig für den erzielten Zusatznutzen.

**Pool-Größe:** Fest auf 4 Worker begrenzt (neue Konstante `PHOTO_PROCESSING_MAX_WORKERS = 4` in `app/core/config.py` oder direkt im jeweiligen Router-Modul) - verhindert CPU-Überlastung durch zu viele gleichzeitige MediaPipe-Inferenzen auf dem begrenzten Railway-Container.

## `/photos/upload`

Aktuell: `for upload in files: <lokal schreiben>; push(...)` - jeder Push blockiert den nächsten.

Neu: Zuerst ALLE Dateien synchron und schnell lokal schreiben (reine Disk-I/O, kein Netzwerk, bleibt sequenziell - ist ohnehin schnell). Danach alle gesammelten `push()`-Aufrufe über den Thread-Pool parallel ausführen, auf deren Abschluss warten, DANN erst `sync_incoming_folder()` aufrufen und antworten. Schlägt ein einzelner Push fehl (Exception in `push()`), wird das wie bisher als harter Fehler behandelt (aktuelles Verhalten von `push()` bei Fehlern: loggt und wirft weiter - siehe `storage_sync.py`) und propagiert als 500, keine stille Teil-Fehler-Verschluckung.

## `/photos/assign-bulk`

Aktuell: `for item in payload.items: _assign_photo(db, photo, pose, ...)` - jeder Aufruf macht intern Datei-Move, bis zu 3 Pushes, MediaPipe-Normalisierung, einen weiteren Push, DB-Commit.

Neu: `_assign_photo` wird in zwei Teile gesplittet:
- `_process_photo_files(photo, pose, weight_kg) -> _ProcessedPhotoResult`: erledigt ALLES außer DB-Schreiben - Datei-Move, Thumbnail-Erzeugung, alle `push()`-Aufrufe, MediaPipe-Normalisierung. Reine Funktion ohne DB-Session, sicher aus einem Worker-Thread aufrufbar (SQLAlchemy-Sessions sind nicht thread-safe, `db: Session` bleibt strikt im Hauptthread).
- `_apply_processed_result(db, photo, day_log, result)`: übernimmt die von `_process_photo_files` zurückgelieferten Pfade/Status/Landmarks in die DB-Objekte und committet - läuft weiterhin sequenziell im Hauptthread (DB-Commits sind ohnehin schnell, kein Parallelisierungsgewinn nötig, aber Session-Sicherheit erzwungen).

`assign_photos_bulk` sammelt zuerst alle gültigen `(photo, pose, weight_kg)`-Tripel (die bestehende Validierung: Foto/Pose existiert, Status ist UNPROCESSED - unverändert), reicht sie über `ThreadPoolExecutor.submit()` an `_process_photo_files` weiter, wartet mit `as_completed()` auf alle Ergebnisse, und wendet sie DANACH nacheinander im Hauptthread über `_apply_processed_result` an. Der `DayLog`-Vorab-Lookup/Erstellung (aktuell Teil von `_assign_photo`, DB-lastig) bleibt ebenfalls im Hauptthread, VOR dem Dispatch an den Thread-Pool - jedes `_process_photo_files`-Ergebnis bekommt die bereits aufgelöste `day_log`-ID mit übergeben, da mehrere Fotos desselben Tages sich sonst beim parallelen Anlegen desselben `DayLog`-Eintrags in die Quere kommen könnten (Race Condition vermieden durch Vorab-Serialisierung dieses einen Schritts).

Einzelfoto-Fehler (z.B. MediaPipe erkennt keine Landmarks) führen weiterhin NUR zu `ProcessingStatus.NORMALIZATION_FAILED` für dieses eine Foto (bestehendes Verhalten, unverändert) - kein Abbruch des gesamten Batches.

## Einzel-Zuordnung (`/photos/{photo_id}/assign`)

Bleibt unverändert (ein einzelnes Foto profitiert nicht von Parallelisierung) - ruft weiterhin `_process_photo_files` + `_apply_processed_result` sequenziell für das eine Foto auf (Wiederverwendung derselben aufgeteilten Funktionen, kein Duplicate-Code).

## Fehlerverhalten

Kein neues Fehlerverhalten gegenüber heute: Erfolg/Fehlschlag pro Foto bleibt identisch zur aktuellen Logik, nur die Reihenfolge/Parallelität der Ausführung ändert sich. Ein kompletter Thread-Pool-Worker-Crash (z.B. Exception in `_process_photo_files`) wird über `future.result()` beim Einsammeln erneut geworfen und muss vom aufrufenden Code abgefangen werden, um wie bisher zu einem sauberen Überspringen dieses einzelnen Fotos zu führen (analog zum bestehenden "einzelne fehlerhafte Einträge werden übersprungen"-Verhalten in `assign_photos_bulk`).

## Out of Scope

- Kein Hintergrund-/Async-Queue-Mechanismus für R2-Uploads (bewusst abgelehnt - siehe Diskussion).
- Keine Änderung an Bildkompression, Thumbnail-Auflösung, oder der MediaPipe-Modellwahl selbst.
- Kein Caching/Wiederverwendung von MediaPipe-Modell-Instanzen über Requests hinweg (bereits Modul-Level-Singleton, siehe `_landmarker` in `pose_normalization.py` - unverändert).

## Testing-Ansatz

- Backend: Unit-Test für `_process_photo_files`/`_apply_processed_result`-Split (Verhalten identisch zum bisherigen `_assign_photo` bei Erfolg und bei MediaPipe-Fehlschlag). Test für `assign_photos_bulk`, der mehrere Fotos gleichzeitig zuordnet und prüft, dass alle korrekt in der DB landen (inkl. desselben Tages ohne doppelten `DayLog`). Test, der `push()` künstlich langsam macht (`monkeypatch` mit `time.sleep`) und misst, dass ein 3-Foto-Batch schneller als 3x die Einzeldauer durchläuft (Nachweis der tatsächlichen Parallelität, nicht nur Code-Struktur).
- Manuell: echten Batch-Upload + "Alle zugeordneten speichern" auf Staging mit mehreren Fotos durchführen, gefühlte Dauer beobachten.
