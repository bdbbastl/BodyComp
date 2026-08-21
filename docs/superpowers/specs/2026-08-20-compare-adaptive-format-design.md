# Compare: Adaptives Seitenverhältnis & Big Mode — Design

## Ziel

Die Compare-Ansicht erzwingt heute für jedes Foto ein festes Container-
Verhältnis von 3:4. Echte Ganzkörper-Fotos (Handyfotos, deutlich
hochkantiger als 3:4) werden dadurch oben/unten beschnitten — Kopf und
Füße fehlen regelmäßig. Zoom kann das nicht ausgleichen, weil
`ZOOM_MIN = 1` kein Verkleinern erlaubt, nur Vergrößern.

Nach diesem Umbau berechnet sich die Container-Form aus den echten
Pixelmaßen beider verglichener Fotos, mit manueller Preset-
Nachjustierung; Zoom kann auch unter 100% gehen; ein neuer "Big Mode"
zeigt den aktuellen Vergleich bildschirmfüllend; und alle Steuerungs-
Icons bekommen sichtbaren Text statt nur Tooltip.

**Leitprinzip, das den gesamten Entwurf durchzieht:** Live-Vorschau, Big
Mode und Export müssen exakt dieselbe Geometrie zeigen — eine einzige
Berechnung, nicht drei separate Annäherungen. Genau dieses Prinzip
wurde beim vorherigen Compare-Export-Bugfix schmerzhaft erarbeitet
(drei Anläufe, bis Live-Vorschau und Export übereinstimmten); dieser
Entwurf baut bewusst darauf auf, statt es zu wiederholen.

## Umfang

1. Seitenverhältnis wird aus den echten Fotomaßen beider Bilder
   berechnet (nicht mehr fest 3:4)
2. Manuelle Preset-Auswahl (Auto / 3:4 / 4:5 / 9:16) als Override
3. Zoom-Bereich erweitert auf 0,5×–6× (bisher 1×–6×)
4. Neuer "Big Mode": bildschirmfüllende Vorschau des aktuellen
   Vergleichs, mit Posen-Navigation
5. Sichtbare Textlabels neben allen Steuerungs-Icons (Header + Pane-
   Reglerzeile)

Betrifft beide Compare-Modi (Side-by-Side und Slider) sowie den
bestehenden Export.

## Architektur

### 1. Seitenverhältnis-Berechnung

**Neue Datei: `frontend/src/utils/compareAspect.ts`**

```typescript
export type AspectPreset = "auto" | "3:4" | "4:5" | "9:16";

export const ASPECT_PRESETS: Record<Exclude<AspectPreset, "auto">, number> = {
  "3:4": 3 / 4,
  "4:5": 4 / 5,
  "9:16": 9 / 16,
};

const FALLBACK_RATIO = 3 / 4; // heutiges Verhalten, falls Fotomaße fehlen
const AUTO_MIN_RATIO = 9 / 16; // schmalste erlaubte Auto-Form
const AUTO_MAX_RATIO = 4 / 5; // breiteste erlaubte Auto-Form

export function resolveAspectRatio(
  preset: AspectPreset,
  photoX: Pick<Photo, "width" | "height"> | undefined,
  photoY: Pick<Photo, "width" | "height"> | undefined
): number
```

Bei `preset !== "auto"` wird der feste Preset-Wert zurückgegeben (nicht
geklemmt — eine bewusste Nutzerwahl wird nicht korrigiert). Bei `"auto"`:

- Fehlen `width`/`height` bei einem der beiden Fotos (alte, nicht
  nachgetragene Datensätze) → `FALLBACK_RATIO` (heutiges Verhalten)
- Sonst: `ratioX = width/height` je Foto, Zielverhältnis =
  `Math.min(ratioX, ratioY)` — das hochkantigere Foto bestimmt die
  Form, das andere verliert höchstens Rand links/rechts, nie Kopf oder
  Füße
- Das Ergebnis wird auf `[AUTO_MIN_RATIO, AUTO_MAX_RATIO]` geklemmt —
  bewusst identisch zu den Grenzen der manuellen Presets (9:16 bis
  4:5), damit die Automatik nie eine extremere Form erzeugt als die
  Presets selbst anbieten. Verhindert, dass ein falsch rotiertes oder
  extrem verzerrtes Foto die Box absurd verformt.

### 2. Datenmodell

Backend liefert `width`/`height` bereits über `PhotoOut`
(`backend/app/schemas/photo.py`) im Comparisons-Endpoint — keine
Backend-Änderung nötig.

**Modify: `frontend/src/types/index.ts`** — `Photo`-Interface bekommt
`width: number | null` und `height: number | null`.

### 3. Anwendung der Form auf die Panes

`Compare()` hält einen neuen State `formatPreset: AspectPreset`
(Default `"auto"`), der **über Posen-/Datumswechsel hinweg bestehen
bleibt** — der User hat ihn bewusst gewählt, ein Wechsel des Fotopaars
setzt ihn nicht zurück. Dieser eine Preset-Wert gilt global für die
ganze Seite.

`ZoomPane` und `SliderComparePane` bekommen eine neue Pflicht-Prop
`aspectRatio: number` und ersetzen ihre feste Tailwind-Klasse
`aspect-[3/4]` durch einen Inline-Style `style={{ aspectRatio }}`.

**Wichtig — zwei unterschiedliche Rendering-Situationen:**

- **Einzelpose** (Side-by-Side/Slider, `!isAllPoses`): `Compare()`
  berechnet `aspectRatio` einmal über
  `resolveAspectRatio(formatPreset, result.photo_x, result.photo_y)`
  und reicht denselben Wert an beide `ComparePane`-Instanzen bzw. die
  eine `SliderComparePane`-Instanz durch — dieselbe Form für beide
  Bilder eines Paares, sonst wäre der Seitenvergleich optisch verzerrt.
- **"All poses"** (`isAllPoses`): Hier rendert `Compare()` bereits
  heute eine `ComparePane`-Zeile **pro Pose** über
  `allPosePairs.map(({ pose, photoX, photoY }) => ...)`. Der
  `aspectRatio`-Wert wird deshalb **pro Zeile einzeln** über
  `resolveAspectRatio(formatPreset, photoX, photoY)` berechnet — jede
  Pose hat ihr eigenes Fotopaar und damit potenziell ihre eigene
  Auto-Form. Der `formatPreset` selbst (Auto oder ein manuelles Preset)
  ist weiterhin ein einziger globaler Wert; nur das *Ergebnis* der
  Auto-Berechnung unterscheidet sich pro Zeile.

Da `getExportState()` die Container-Maße bereits live über
`getBoundingClientRect()` liest (siehe vorheriger Export-Bugfix), ist
hier **keine Änderung an `compareExport.ts`s Platzierungs-Mathematik
nötig** — sie funktioniert bereits korrekt mit jeder Container-Form.

**Neue UI:** `CompareFilterBar` bekommt eine vierte Gruppe „Format"
(Chips: Auto / 3:4 / 4:5 / 9:16), platziert links neben dem
Modus-Umschalter, mit demselben visuellen Muster wie die bestehenden
Gruppen (Label + Auswahl-Control).

### 4. Zoom unter 100%

`usePanZoom` ist ein **geteilter** Hook — auch `PhotoLightbox.tsx`
(Timeline/Check-ins, ein unabhängiges Feature) nutzt ihn mit dem
globalen `ZOOM_MIN`/`ZOOM_MAX`. Eine globale Absenkung von `ZOOM_MIN`
hätte dort einen unbeabsichtigten Nebeneffekt. Stattdessen wird der
Wert konfigurierbar:

**Modify: `frontend/src/hooks/usePanZoom.ts`** — `usePanZoom(options?:
{ zoomMin?: number })`, intern verwendet als unterer Klemm-Wert in
`applyZoomAtPoint` statt der festen Konstante `ZOOM_MIN`. Default bleibt
`ZOOM_MIN` (`1`) — bestehende Aufrufer (`PhotoLightbox`) ändern sich
nicht. `ZoomPane` und `SliderComparePane` rufen `usePanZoom({ zoomMin:
0.5 })` auf.

**Modify: `frontend/src/components/ZoomSlider.tsx`** — analog ein
optionales `min?: number`-Prop (Default `ZOOM_MIN`), da der Regler
denselben unteren Wert wie der zugehörige Pan/Zoom-Zustand erlauben
muss. `PaneAdjustments` übergibt `min={0.5}`; `PhotoLightbox`s
Verwendung bleibt unverändert (kein `min`-Prop, Default greift).

Bei Zoom < 1 füllt das Foto seine Box nicht mehr vollständig aus; der
sichtbare Hintergrund dahinter muss dieselbe Farbe zeigen wie der
Export-Canvas-Hintergrund (`#0b0f14`), damit Live-Vorschau und Export
auch hier optisch übereinstimmen. `ZoomPane`- und
`SliderComparePane`-Container bekommen diese Hintergrundfarbe (aktuell
`bg-black/40`, wird zu einer deckenden `#0b0f14`-Fläche für den
Letterbox-Fall).

`compareExport.ts`s `drawPhotoIntoRegion` braucht hierfür **keine
Änderung** — sie multipliziert `state.scale` bereits korrekt in die
Bildgröße ein; ein Wert < 1 verkleinert das gezeichnete Bild einfach
innerhalb der bereits mit `#0b0f14` gefüllten Canvas-Fläche.

### 5. Big Mode

**Refactor: `frontend/src/utils/compareExport.ts`**

Bisher nehmen `renderSideBySideToCanvas`/`renderSliderToCanvas` einen
`aspect: ExportAspect` entgegen und schlagen darüber feste Maße in
`EXPORT_DIMENSIONS` nach. Das wird verallgemeinert, ohne die
bestehenden Aufrufer (Export-Modal, bestehende Tests) zu brechen:

```typescript
export type ExportAspect = "1:1" | "4:3";
type TargetDimensions = { width: number; height: number };

export function resolveDimensions(target: ExportAspect | TargetDimensions): TargetDimensions {
  if (typeof target === "string") return EXPORT_DIMENSIONS[target];
  return target;
}
```

`renderSideBySideToCanvas`/`renderSliderToCanvas` nehmen fortan
`target: ExportAspect | TargetDimensions` statt `aspect: ExportAspect`
und rufen intern `resolveDimensions(target)` auf. Die zwei bestehenden
Export-Formate (`"1:1"`, `"4:3"`) funktionieren unverändert; Big Mode
übergibt stattdessen ein `{ width, height }`-Objekt: die größtmögliche
Fläche des verfügbaren Vollbild-Bereichs (Viewport abzüglich der
Header-Leiste und etwas Rand), die `aspectRatio` exakt einhält — analog
zu CSS `object-fit: contain`, aber als konkrete Pixelmaße für die
Canvas-Auflösung, damit das Ergebnis nicht unscharf hochskaliert wird.

**Neue Datei: `frontend/src/components/CompareBigMode.tsx`**

Vollbild-Overlay nach dem Muster von `PhotoLightbox.tsx` (`fixed
inset-0`, `bg-black/90`-Backdrop, Escape/Backdrop-Klick/×-Button zum
Schließen). Zeigt oben eine schmale Leiste im Foto-Galerie-Stil:
Posenname mittig, ‹/›-Pfeile links/rechts (rufen dieselbe
`onNavigate`/`goToPose`-Funktion wie `CompareFilterBar` auf), ×-Button
rechts. Darunter füllt ein `<canvas>` den verfügbaren Platz.

Big Mode ist **keine eigene Zoom-/Pan-Oberfläche** — er zeigt den
aktuellen Stand der Panes (Zoom, Pan, Neigung, Belichtung, Format), wie
er in der kleinen Ansicht eingestellt wurde, vergrößert. Trennlinie im
Slider-Modus ist statisch (wie im Export), nicht ziehbar. **Kein
Wasserzeichen** — Big Mode ist reine In-App-Vorschau, kein teilbarer
Download.

Um das Leitprinzip (eine Geometrie überall) einzuhalten, teilen sich
Export-Modal und Big Mode **denselben Render-Callback**: `Compare.tsx`s
bestehende `handleExportRender`-Funktion (liest die Live-Geometrie über
`paneXRef`/`paneYRef`/`sliderPaneRef`, lädt die Bilder, ruft
`renderSideBySideToCanvas`/`renderSliderToCanvas` auf) wird um einen
`showWatermark`-Parameter erweitert und von beiden Komponenten
aufgerufen — Big Mode übergibt `showWatermark={false}` und ein
Big-Mode-spezifisches `TargetDimensions`-Objekt statt eines
`ExportAspect`.

Big Mode reagiert auf Posenwechsel (neue `result`-Daten → neue Bilder
laden → neu zeichnen, gleiches Muster wie beim initialen Rendern) und
auf Fenstergrößenänderung (Canvas-Zieldimensionen neu berechnen,
neu zeichnen).

**Auslöser:** neues Icon im Header (`Maximize2` aus `lucide-react`,
Label „Groß anzeigen"), platziert bei den Ansichts-Toggles (Scan,
Grid3x3), vor dem bestehenden Trennstrich zu den Aktionen (KI/Export).

Wie der Export-Button ist Big Mode **nur bei Einzelpose verfügbar**
(`!isAllPoses && result`) — im "All poses"-Modus werden bereits alle
Posen gleichzeitig als Liste gezeigt, ein Vollbild-Modus für eine
einzelne Pose passt dort konzeptionell nicht und wird nicht angeboten
(dasselbe Muster wie beim bestehenden Export-Icon).

### 6. Sichtbare Icon-Labels

**Modify: `frontend/src/components/IconButton.tsx`** — das bestehende
`label`-Prop bleibt (liefert weiterhin `aria-label`/`title`), ein neues
optionales Prop `showLabel?: boolean` (Default `false`) rendert
denselben Text zusätzlich sichtbar **rechts neben dem Icon** in der
Button-Fläche (Icon behält seine Größe, Button wird zum Icon+Text-Chip
statt einer reinen Quadratfläche).

Alle Aufrufstellen (Header-Actions in `Compare.tsx`, Icon-Reihe in
`PaneAdjustments.tsx`) setzen `showLabel` künftig auf `true`. Kurze,
prägnante sichtbare Texte statt der vollen Tooltip-Erklärung, z.B.:

| Tooltip (`label`, unverändert) | Sichtbarer Text (neu) |
|---|---|
| KI-Normalisierung (Ausrichtung & Skalierung) | KI-Norm. |
| Ausrichtungsgitter | Gitter |
| Groß anzeigen | Groß |
| KI-Analyse (Judge-Bewertung) | KI-Analyse |
| Vergleich exportieren | Export |
| Zoom | Zoom |
| Neigung | Neigung |
| Position | Position |
| Exposure | Exposure |
| Alles zurücksetzen | Reset |

Da Buttons dadurch breiter werden, prüft die Implementierung, ob die
Header- und Pane-Reihen bei sechs bzw. fünf Icon+Text-Chips noch in
eine Zeile passen (Viewport-Referenz: Desktop, siehe frühere
Compare-Steuerungsbereich-Spec) — bei Bedarf `flex-wrap` statt
horizontalem Overflow.

## Out of Scope

- Persistenz der Format-Wahl über die Session hinaus (kein Speichern
  in Client-Einstellungen oder Datenbank)
- Live-Editierbarkeit (Zoom/Pan/Neigung) innerhalb des Big Mode selbst
- Ziehbare Trennlinie im Big-Mode-Slider
- Mobile-spezifische Optimierung von Big Mode oder den Format-Chips
- Wasserzeichen-Bug im Export (separat als eigene Aufgabe erfasst)
- Rückwirkendes Nachtragen fehlender `width`/`height` bei alten Fotos
  (passiert bereits automatisch beim nächsten Ordner-Sync, siehe
  `folder_sync.py`)

## Verifikation

- `npx tsc --noEmit`, `npm test` (bestehende `compareExport`-Tests
  bleiben grün; neue Tests für `resolveAspectRatio` und
  `resolveDimensions` kommen hinzu)
- Browser-Check: Fotopaar mit deutlich unterschiedlichen natürlichen
  Seitenverhältnissen (z.B. ein hochkantiges Handyfoto, ein
  quadratischeres) — Auto-Form zeigt beide vollständig von Kopf bis
  Fuß; Format-Chips wechseln die Form sichtbar; Zoom-Regler geht bis
  0,5× mit sichtbarem Letterboxing (nur in Compare — `PhotoLightbox`
  bleibt bei 1×–6× wie bisher); Big Mode öffnet bildschirmfüllend mit
  identischer Bildplatzierung wie die kleine Vorschau, ist aber im "All
  poses"-Modus nicht verfügbar (wie der Export-Button); Export-Download
  zeigt exakt denselben Ausschnitt wie Big Mode und Live-Vorschau; "All
  poses"-Ansicht zeigt pro Posen-Zeile eine an das jeweilige Fotopaar
  angepasste Auto-Form; alle Icon-Buttons zeigen sichtbaren Text
