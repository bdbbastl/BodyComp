# Thumbnail-Prefetch + Check-in-Löschen (Coach) — Design-Spec

**Datum:** 2026-08-19
**Status:** Genehmigt

## Kontext

Zwei unabhängige, aber zusammen umzusetzende Verbesserungen aus Live-Feedback:

1. **Thumbnail-Ladeperformance:** Railways Container-Plattenspeicher wird bei jedem Deploy geleert. `ensure_local()` (siehe `backend/app/services/storage_sync.py`) lädt fehlende Dateien bei Bedarf von R2 nach - aktuell passiert das erst beim einzelnen `/media`-Request pro Foto, wodurch Thumbnails auf der Timeline nach jedem Deploy erst nach 1-2s Verzögerung und dann nacheinander (statt sofort) laden. Eine dauerhafte Lösung per persistentem Volume wurde bewusst abgelehnt (Kostengründe) - stattdessen wird das Nachladen selbst parallelisiert.
2. **Check-in löschen:** Der Coach hat aktuell keine Möglichkeit, eine fehlerhafte/unbrauchbare Check-in-Einreichung samt Fotos zu entfernen (akuter Fall: ein bereits "reviewed" Check-in von VOR der Pose-Zuordnungs-Änderung, das nicht mehr sinnvoll verwertbar ist).

## Ziel

1. Timeline/Client-Dashboard laden nach einem Cold-Start (frischer Deploy) alle sichtbaren Thumbnails parallel statt seriell nach.
2. Der Coach kann eine Check-in-Einreichung samt aller zugehörigen Fotos vollständig löschen.

## Teil 1: Server-seitiges Parallel-Prefetch für Thumbnails

### `backend/app/routers/photos.py`, Funktion `list_photos`

Bevor die Foto-Liste zurückgegeben wird, werden alle noch nicht lokal vorhandenen `thumb_path`-Dateien der Ergebnismenge parallel per `ThreadPoolExecutor` nachgeladen (gleiches Muster wie `PHOTO_PROCESSING_MAX_WORKERS` an anderer Stelle im selben Modul):

```python
THUMBNAIL_PREFETCH_MAX_WORKERS = 8

def _prefetch_thumbnails(thumb_paths: list[str]) -> None:
    """Lädt fehlende Thumbnails parallel von R2 nach, BEVOR die Foto-Liste
    zurückgegeben wird - ensure_local() ist idempotent (No-Op wenn schon
    lokal vorhanden), hier wird nur die fehlenden Fälle betroffen. Ohne
    dieses Prefetch würde jeder einzelne /media-Request sein eigenes
    R2-Download auslösen, was nach jedem Redeploy (ephemeres Railway-
    Dateisystem) zu sequenziell wirkendem, langsamem Thumbnail-Laden auf
    der Timeline führt - siehe Design-Spec."""
    missing = [p for p in set(thumb_paths) if p and not (settings.data_dir / p).exists()]
    if not missing:
        return
    with ThreadPoolExecutor(max_workers=THUMBNAIL_PREFETCH_MAX_WORKERS) as executor:
        list(executor.map(ensure_local, missing))
```

Aufruf am Ende von `list_photos`, direkt vor dem `return`: `_prefetch_thumbnails([p.thumb_path for p in results])` (Feldname im tatsächlichen Code prüfen - `thumbnail_path`/`thumb_path`, je nach Modell).

- Nur `thumb_path`/`thumbnail_path` wird vorab geladen, NICHT `original_path`/`normalized_path` - die Timeline zeigt nur Thumbnails, größere Bilder werden erst bei Bedarf geladen (z.B. Compare).
- Läuft synchron innerhalb des Requests (die Liste kommt entsprechend etwas später zurück), aber parallelisiert über alle fehlenden Dateien statt seriell über N einzelne `/media`-Requests.
- Einzelne fehlgeschlagene Downloads werden wie bisher in `ensure_local` geloggt und ignoriert (kein harter Fehler für die ganze Liste).

### Frontend

Keine Änderung nötig - Timeline/SingleDashboard rufen weiterhin `mediaUrl(photo.thumb_path)`, die `/media`-Requests treffen jetzt nur noch auf bereits lokal vorhandene Dateien.

## Teil 2: Check-in löschen (Coach)

### `backend/app/routers/checkins.py`

Neuer Endpunkt, gleiches Präfix/Ownership-Schema wie die bestehenden Routen:

```python
@router.delete("/{checkin_id}", status_code=204)
def delete_checkin(
    checkin_id: int, client_row: Client = Depends(get_owned_client), db: Session = Depends(get_db)
):
    """Löscht einen Check-in samt aller zugehörigen Fotos (Dateien +
    DB-Zeilen) unwiderruflich. Der DayLog-Eintrag (Gewicht/Notizen) bleibt
    bestehen - Gewicht ist ein Tages-, kein Check-in-Attribut, konsistent
    mit delete_photo() in photos.py."""
    submission = (
        db.query(CheckinSubmission)
        .filter(CheckinSubmission.id == checkin_id, CheckinSubmission.client_id == client_row.id)
        .first()
    )
    if not submission:
        raise HTTPException(404, "Check-in not found")

    photos = db.query(Photo).filter(Photo.checkin_submission_id == checkin_id).all()
    for photo in photos:
        _delete_photo_files(photo)
        db.delete(photo)
    db.delete(submission)
    db.commit()
```

Importiert `_delete_photo_files` und `Photo` aus `app.routers.photos` (bzw. verschiebt die Funktion nach `app.services` falls ein Import-Zyklus entsteht - im Zweifel beim Implementieren prüfen, `photos.py` importiert aktuell nichts aus `checkins.py`, ein direkter Import sollte unproblematisch sein).

### Frontend (`frontend/src/pages/ClientCheckins.tsx`)

Pro Check-in-Karte ein "Delete"-Button (rotes/Danger-Styling). Klick zeigt eine Inline-Bestätigung ("Delete this check-in and its photos permanently?" + Confirm/Cancel-Buttons), kein natives `confirm()`. Nach erfolgreichem Löschen: die `checkins`-Query wird invalidiert, UND zusätzlich die `photos`-Query-Keys (Timeline/Compare könnten die zugehörigen Fotos bereits sichtbar gehabt haben, falls der Check-in `reviewed` war).

### `frontend/src/api/client.ts`

Neue Methode im `checkins`-Namespace (oder wo `list`/`update` aktuell liegen): `delete: (clientId: number, checkinId: number) => client.delete(\`/clients/${clientId}/checkins/${checkinId}\`)`.

## Out of Scope

- Kein persistentes Railway-Volume (bewusst abgelehnt).
- Kein CDN/Presigned-URL-Redirect für Bildauslieferung.
- Kein Prefetch für `original_path`/`normalized_path` (nur Thumbnails).
- Kein Undo/Papierkorb für gelöschte Check-ins.
- Kein Massenlöschen mehrerer Check-ins auf einmal.

## Testing-Ansatz

- Backend: Test, dass `list_photos` nach Prefetch alle angefragten Thumbnails lokal vorliegen hat (Monkeypatch/Fake für `ensure_local`, prüfen dass es für jede fehlende Datei aufgerufen wird - ähnlich dem bestehenden Parallelitäts-Test aus Stufe 7a). Test für `delete_checkin`: löscht Submission + zugehörige Fotos (DB-Zeilen UND Dateien), 404 bei unbekannter ID/fremdem Klienten, DayLog bleibt unverändert.
- Frontend: `npx tsc --noEmit`; manuell: Delete-Button + Inline-Bestätigung funktioniert, Check-in verschwindet aus der Liste, zugehörige Fotos verschwinden aus Timeline/Compare falls vorher sichtbar.
