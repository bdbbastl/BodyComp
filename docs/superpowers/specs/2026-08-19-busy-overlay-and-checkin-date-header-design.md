# Ladeanzeige für langsame Aktionen + Tag/KW-Header — Design-Spec

**Datum:** 2026-08-19
**Status:** Genehmigt

## Kontext

Mehrere datenverarbeitende Aktionen im Frontend geben aktuell kein Feedback während der Server-Verarbeitung - akuter Fall: das Löschen eines Check-ins dauert ~10s (Fotodateien lokal + R2), ohne dass der User sieht, dass überhaupt etwas passiert. Es gibt bereits einen fertigen, App-weiten `BusyOverlayContext`/`BusyOverlay` (Spinner + Label, optional Fortschrittsbalken, kein Abbrechen-Button - siehe `frontend/src/contexts/BusyOverlayContext.tsx`), der bereits in `Unprocessed.tsx` für Upload/Bulk-Save genutzt wird, aber nicht flächendeckend.

Zusätzlich: auf der Magic-Link Check-in-Seite und in der Coach-Check-ins-Ansicht fehlt über den Fotos der Tag/KW-Kontext, den die Timeline bereits zeigt (`formatDateWithWeek`/`formatDateShortWithWeek` in `frontend/src/utils/date.ts`).

## Ziel

1. Vier identifizierte langsame Aktionen zeigen während der Verarbeitung das bestehende `BusyOverlay`.
2. Magic-Link-Seite und Coach-Check-ins-Ansicht zeigen über den Fotos denselben Tag/KW-Header wie die Timeline.

## Teil 1: BusyOverlay für vier Aktionen

Alle vier nutzen den bestehenden `useBusyOverlay()`-Hook (`show(label)` beim Mutation-Start, `hide()` in sowohl `onSuccess` als auch `onError` der jeweiligen Mutation, damit das Overlay auch bei einem Fehlschlag wieder verschwindet).

### `frontend/src/pages/ClientCheckins.tsx` - `deleteMutation`

`show("Deleting check-in…")` beim `mutate()`-Aufruf (bzw. im `onMutate` der Mutation), `hide()` in `onSuccess` (zusätzlich zu den bestehenden Invalidierungen) und in einem neuen `onError`.

### `frontend/src/pages/CheckinSubmit.tsx` - `submitMutation`

Diese Seite liegt AUSSERHALB von `AppShell`/`ClientShell`, aber innerhalb von `BusyOverlayProvider` (das umschließt in `App.tsx` bereits alle Routen, inklusive der öffentlichen). `useBusyOverlay()` ist also nutzbar. `show("Submitting check-in…")` beim Absenden, `hide()` in `onSuccess`/`onError`.

### `frontend/src/pages/Timeline.tsx` - `deleteMutation` (einzelnes Foto) und `deleteDayMutation` (ganzer Tag)

`show("Deleting photo…")` bzw. `show("Deleting day…")`, jeweils `hide()` in `onSuccess`/`onError`.

### `frontend/src/pages/Compare.tsx` - `aiAnalysisMutation` und `aiAnalysisAllMutation`

`show("Judge analyzing…")` bei Start beider Mutationen, `hide()` in `onSuccess`/`onError`. Der bestehende Button-Text ("Judge analyzing…" während `isPending`) bleibt zusätzlich bestehen - das Overlay ist eine ergänzende, nicht ersetzende Anzeige.

## Teil 2: Tag/KW-Header über den Fotos

Wiederverwendung der bestehenden Utility-Funktionen aus `frontend/src/utils/date.ts`, keine neue Formatierungslogik.

### `frontend/src/pages/CheckinSubmit.tsx`

Über dem Foto-Upload-Bereich (sichtbar sobald die Seite geladen ist, nicht erst nach Dateiauswahl) wird eine kleine Überschrift mit `formatDateWithWeek(new Date().toISOString())` angezeigt - der Tag, für den eingereicht wird, ist immer das aktuelle lokale Datum des Client-Geräts (kein Datumsfeld im Formular, das ändern würde).

### `frontend/src/pages/ClientCheckins.tsx`

Pro Check-in-Karte, direkt über der bestehenden Foto-Reihe (innerhalb des vorhandenen `{checkin.photos.length > 0 && (...)}`-Blocks, als erstes Kind davor), wird `formatDateShortWithWeek(checkin.submitted_at)` als kleine Überschrift ergänzt (kompaktere Variante, passend zur Kartenoptik).

## Out of Scope

- Kein Fortschrittsbalken mit Prozentanzeige für die vier neuen Aktionen (nur Spinner+Label wie das bestehende Muster ohne Upload-Fortschritt).
- Keine Änderung an Account-Löschung/-Export (nicht Teil der ausgewählten Aktionen).
- Keine Änderung an der bestehenden `updateMutation`/"Mark as reviewed"/"Save feedback" in `ClientCheckins.tsx` (nicht ausgewählt, gilt als schnell genug).
- Kein Datumsauswahlfeld auf der Magic-Link-Seite - der Header zeigt nur informativ das aktuelle Datum, ist nicht interaktiv.

## Testing-Ansatz

- Frontend: `npx tsc --noEmit`. Manuell: jede der vier Aktionen auslösen und prüfen, dass das Overlay während der Verarbeitung erscheint und danach (Erfolg UND Fehlerfall) wieder verschwindet; Magic-Link-Seite zeigt den heutigen Tag/KW-Header schon vor Dateiauswahl; Coach-Check-ins-Ansicht zeigt pro Check-in mit Fotos den korrekten Tag/KW-Header basierend auf `submitted_at`.
