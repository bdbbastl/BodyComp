# Check-in-Sichtbarkeit + Compare-Performance-Paket — Design-Spec

**Datum:** 2026-08-19
**Status:** Genehmigt

## Kontext

Fünf unabhängige, aber zusammen umzusetzende UX-Verbesserungen aus Live-Feedback: bessere Sichtbarkeit offener Check-ins (Nav-Badge, Dashboard-Widget-Zähler + klickbare Zeilen statt Button), ein Herkunfts-Indikator pro Timeline-Foto (Coach-Upload vs. Client-Check-in), und zwei Compare-Verbesserungen (Pose-Switcher erst nach Datumsauswahl, ruckelfreies Pose-Wechseln).

## Ziel

1. Der Coach sieht auf einen Blick (Nav + Dashboard), wie viele offene Check-ins ein Kunde/insgesamt hat.
2. Das "Unseen check-ins"-Widget wird direkt zur Check-ins-Seite klickbar, ohne separaten "Mark seen"-Button.
3. Jedes Foto in der Timeline zeigt, ob es vom Coach hochgeladen oder über einen Client-Check-in eingereicht wurde.
4. Der Pose-Switcher in Compare erscheint erst, wenn beide Vergleichsdaten gewählt sind.
5. Pose-Wechsel in Compare fühlen sich flüssig an, nicht ruckelig/leer während des Ladens.

## Teil 1: Nav-Badge für offene Check-ins (`frontend/src/components/ClientShell.tsx`)

Kein Backend nötig - `clientQuery.data.pending_checkins_count` ist bereits Teil von `ClientOut` und wird in `ClientShell` bereits geladen (`clientQuery`). Der "Check-ins"-Nav-Punkt bekommt einen roten Kreis mit der Zahl, nur sichtbar wenn `pending_checkins_count > 0`:

```tsx
{item.to === "checkins" && (clientQuery.data?.pending_checkins_count ?? 0) > 0 && (
  <span className="ml-auto flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold text-white">
    {clientQuery.data!.pending_checkins_count}
  </span>
)}
```

Eingefügt in `renderNavItem` innerhalb des `<NavLink>`, nach `{!options.collapsed && item.label}`. Im eingeklappten Zustand (`collapsed`) wird die Zahl trotzdem gezeigt (kleiner Kreis reicht dort als reiner Indikator, kein Platz für Label+Zahl nötig).

`renderNavItem` braucht dafür Zugriff auf `clientQuery.data` - entweder als zusätzlichen Parameter durchgereicht oder (einfacher, da `renderNavItem` bereits eine Closure innerhalb der Komponente ist) direkt auf die im Closure verfügbare `clientQuery` zugreifen.

## Teil 2: Dashboard "Unseen check-ins"-Widget (`frontend/src/pages/Dashboard.tsx`)

### Zähler im Card-Titel

`Card`s `title`-Prop wird von `string` auf `ReactNode` erweitert (`frontend/src/components/Card.tsx`) - rückwärtskompatibel, da ein `string` ein gültiger `ReactNode` ist. `PendingCheckinsWidget` übergibt einen zusammengesetzten Titel:

```tsx
<Card
  title={
    <span className="flex items-center gap-2">
      Unseen check-ins
      {items.length > 0 && (
        <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1 text-xs font-semibold text-white">
          {items.length}
        </span>
      )}
    </span>
  }
>
```

### Klickbare Zeilen statt "Mark seen"-Button

`markSeenMutation` wird entfernt (überflüssig - siehe unten). Jede Zeile wird ein `<Link to={`/clients/${item.client_id}/checkins`}>`, gleiches Hover-Highlight-Muster wie `ClientsWidget`s Zeilen (`hover:bg-white/5`, `rounded-lg`, `px-2 py-1.5`). Ein Check-in verschwindet aus der Liste, sobald der Coach ihn auf der Check-ins-Seite über den bereits bestehenden "Mark as reviewed"-Flow abschließt (kein separates "seen"-Konzept mehr, ein Klarheitsgewinn gegenüber vorher zwei getrennten Zuständen).

## Teil 3: Timeline-Herkunfts-Indikator

### Backend (`backend/app/schemas/photo.py`)

`PhotoOut` bekommt ein neues Feld:

```python
checkin_submission_id: int | None
```

(Direkt aus dem bereits vorhandenen `Photo.checkin_submission_id`-Modellfeld übernommen - `from_attributes = True` erledigt das automatisch, keine weitere Backend-Logik nötig.)

### Frontend (`frontend/src/types/index.ts`, `frontend/src/pages/Timeline.tsx`)

`Photo`-Typ bekommt `checkin_submission_id: number | null`. Jede `PhotoCard` in der Timeline zeigt oben links ein kleines Badge:

```tsx
<span
  title={photo.checkin_submission_id != null ? "From client check-in" : "Uploaded by coach"}
  className="absolute left-2 top-2 flex h-6 w-6 items-center justify-center rounded-full bg-black/60 text-xs backdrop-blur"
>
  {photo.checkin_submission_id != null ? "📨" : "📤"}
</span>
```

Platziert im bereits vorhandenen `relative`-Container von `PhotoCard` (dort, wo auch der "Delete"-Button positioniert ist), linke statt rechte Ecke, damit es nicht mit dem bestehenden Lösch-Button kollidiert.

## Teil 4: Compare - Pose-Switcher erst nach Datumsauswahl

`frontend/src/pages/Compare.tsx`: Die Bedingung für `<PoseNavBar>` wird von `poses.length > 0` auf `poses.length > 0 && dateX !== "" && dateY !== ""` erweitert.

## Teil 5: Compare - ruckelfreies Pose-Switching

`frontend/src/pages/Compare.tsx`:

1. **`keepPreviousData`**: `comparisonQuery` bekommt `placeholderData: keepPreviousData` (TanStack-Query-Import `keepPreviousData` aus `@tanstack/react-query`) - beim Pose-Wechsel bleibt das vorherige Bildpaar sichtbar (leicht abgedunkelt via `comparisonQuery.isFetching`, siehe unten), statt kurz komplett zu verschwinden, während die neuen Daten laden.
2. **Prefetch der Nachbar-Posen**: Ein neuer `useEffect`, der bei jeder `poseSelection`-/Datums-Änderung (nur wenn eine einzelne Pose gewählt ist, nicht bei "Alle Posen") die jeweils vorherige und nächste Pose im `poses`-Array per `queryClient.prefetchQuery` mit demselben Query-Key-Schema wie `comparisonQuery` vorlädt. Das füllt den TanStack-Query-Cache im Hintergrund, sodass ein Klick auf ‹/› meist schon auf bereits geladene Daten trifft.
3. **Bild-Vorwärmen**: Sobald die Vergleichsdaten für die Nachbar-Posen im Cache sind (aus Schritt 2), werden zusätzlich deren Bilddateien per unsichtbarem `new Image().src = mediaUrl(...)` im Browser vorgeladen - das wärmt sowohl den Browser-HTTP-Cache als auch (über den bestehenden `ensure_local`-Mechanismus in `/media`) den lokalen Server-Dateicache vor, analog zum bereits bestehenden Thumbnail-Prefetch-Muster in `list_photos`.

## Out of Scope

- Kein Deep-Linking von der Dashboard-Widget-Zeile direkt zu einem bestimmten, bereits aufgeklappten Check-in (Klick führt zur Check-ins-Seite insgesamt, der Coach klickt dort selbst die Karte auf).
- Keine Änderung an `ClientsWidget`/`NeedsAttentionWidget` (nutzen bereits dasselbe Klick-Muster).
- Kein serverseitiges Änderung/Caching für Compare - alle Performance-Maßnahmen sind rein clientseitig (TanStack-Query-Cache + Browser-Image-Preload).
- Kein Prefetch bei "Alle Posen"-Auswahl (dort gibt es keine "Nachbar-Pose"-Navigation).

## Testing-Ansatz

- Backend: Test, dass `GET /clients/{id}/photos` jetzt `checkin_submission_id` im Response-Body hat (sowohl `None` bei Coach-Uploads als auch die tatsächliche ID bei Check-in-Fotos).
- Frontend: `npx tsc --noEmit`. Manuell: Nav-Badge erscheint/verschwindet korrekt je nach offenen Check-ins; Dashboard-Widget zeigt Zähler, Klick auf eine Zeile navigiert zur Check-ins-Seite, kein "Mark seen"-Button mehr sichtbar; Timeline zeigt das richtige Badge pro Foto; Compare-Pose-Switcher erscheint erst nach beiden Datumsauswahlen; Pose-Wechsel per ‹/› fühlt sich merklich flüssiger an (kein kompletter Blank-State mehr).
