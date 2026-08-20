# Compare-Steuerungsbereich — Redesign — Design

## Ziel

Der Steuerungsbereich der Compare-Seite besteht heute aus drei gestapelten,
mittig zentrierten Blöcken (Filterkarte, Pose-Navigation, zwei große
Aktions-Buttons). Zusammen mit den drei Regler-Zeilen unter jedem Foto
schieben sie die Fotos — den eigentlichen Inhalt der Seite — weit nach
unten.

Nach dem Umbau stehen Export und KI-Analyse als kompakte Icon-Buttons im
Seiten-Header, die Filter in einer einzigen Zeile darunter, und die
Bild-Regler als Icon-Reihe mit Popover. Die Fotos rücken dadurch deutlich
nach oben.

Reine Präsentationsschicht: kein Verhalten der Zoom/Pan-Mechanik, der
Export-Mathematik oder der KI-Aufrufe ändert sich.

## Umfang

Betroffen sind vier Zonen der Compare-Seite:

1. **Filterkarte** — Pose, Datum X, Datum Y, Modus-Umschalter, zwei Checkboxen
2. **Pose-Navigation** (`PoseNavBar`) — entfällt, geht in Zone 1 auf
3. **Aktionen** — KI-Analyse-Button, Export-Button
4. **Bild-Regler** — Zoom, Neigung, Exposure unter jedem Foto

Zielgerät ist Desktop. Mobil bleibt funktionsfähig (gestapelt), wird aber
nicht eigens optimiert.

## Architektur

`Compare.tsx` umfasst derzeit ~1130 Zeilen und vereint Filter, zwei
Pane-Typen, Export und KI-Analyse. Statt die Datei weiter wachsen zu
lassen, werden drei Komponenten herausgelöst. `Compare.tsx` bleibt
Orchestrator: Es besitzt weiterhin Auswahl- und Ansichtszustand (Pose,
Daten, Modus, Normalisierung, Gitter, Exposure) und reicht ihn nach unten
durch. Die neuen Komponenten sind darstellend und halten höchstens
eigenen UI-Zustand (etwa welches Popover offen ist).

### `components/IconButton.tsx`

Ein Icon-Button für alle acht Verwendungen (zwei Header-Toggles, zwei
Header-Aktionen, vier je Pane).

Props: `icon` (lucide-Komponente), `label` (Pflicht — wird `aria-label`
und Tooltip), `onClick`, `variant` (`"ghost" | "accent"`), `active`,
`pending`, `disabled`, `badge`, `dot`.

Zustände:

| Zustand | Darstellung |
|---|---|
| normal | transparenter Rahmen, Slate-Icon |
| `active` (Toggle an) | Accent-Tint, Accent-Rahmen, Accent-Icon |
| `variant="accent"` | voll Accent-Fläche, dunkles Icon |
| `pending` | Spinner statt Icon, Accent-Tint, `disabled` |
| `disabled` | 35 % Deckkraft, `cursor-not-allowed` |
| `dot` | kleiner Accent-Punkt oben rechts (Wert ≠ Standard) |
| `badge` | Zahl oben rechts (Posenanzahl bei „All poses") |

Da die Buttons kein sichtbares Label tragen, ist `label` Pflicht-Prop —
nicht optional. Es liefert `aria-label` und `title` zugleich.

### `components/PaneAdjustments.tsx`

Ersetzt die drei Regler-Zeilen unter jedem Foto durch eine Icon-Reihe:
Zoom, Neigung, Exposure, sowie rechtsbündig Zurücksetzen.

Ein Klick öffnet ein Popover mit genau dem einen Regler (Label,
Zahlenwert, −/+-Stepper, Slider). Ein zweiter Klick auf dasselbe Icon
schließt es; ein Klick auf ein anderes Icon wechselt das Werkzeug.

Die Komponente kapselt ausschließlich, welches Werkzeug offen ist. Sie
hält selbst keinen Reglerwert. Die Werte bleiben genau dort, wo sie heute
liegen — Zoom/Pan und Neigung in `ZoomPane` bzw. `SliderComparePane`,
Exposure als `brightnessX`/`brightnessY` in `Compare.tsx` —, damit die
Ref-basierte Export-Anbindung unberührt bleibt.

Verhalten:

- Escape schließt das Popover
- Klick außerhalb schließt es
- Nur ein Popover je Pane gleichzeitig offen
- Icon trägt einen Punkt, sobald der Wert vom Standard abweicht
  (Zoom ≠ 1, Neigung ≠ 0, Exposure ≠ 100)
- Zurücksetzen setzt alle drei Werte des Panes zurück (Zoom **und** Pan,
  Neigung, Exposure) und ist deaktiviert, solange alle auf Standard
  stehen. Das ist mehr als der heutige Doppelklick, der nur Zoom und Pan
  zurücksetzt; der Doppelklick bleibt unverändert erhalten.

Die Stepper bleiben erhalten. `usePanZoom` dokumentiert ausdrücklich
feine Schrittweiten (0,05 je Rad-Tick, weil gröbere Sprünge für exakte
Bild-zu-Bild-Deckung unbrauchbar waren) — Feinjustierung ist eine
Anforderung, keine Kür.

### `components/CompareFilterBar.tsx`

Eine Zeile: Pose (Dropdown mit ‹ ›-Pfeilen), „Vergleich" als
`Datum X → Datum Y`, rechtsbündig der Modus-Umschalter mit Icons.

Das Pose-Dropdown und die bisherige `PoseNavBar` steuern denselben Wert —
zwei Bedienelemente für eine Größe, die eine ganze Zeile kosten. Die
Pfeile wandern an das Dropdown, `PoseNavBar` wird ersatzlos entfernt.

Die Pfeile übernehmen `goToPose` unverändert. Im Modus „All poses" sind
sie deaktiviert — analog zum heutigen `disabled={isAllPoses}` der
`PoseNavBar`.

`goToPose` läuft per Modulo zyklisch durch die Posenliste; es gibt kein
Anfang oder Ende. Die Pfeile werden daher **nicht** an den Rändern
deaktiviert. Auch die bestehende Pfeiltasten-Steuerung (←/→ auf
Fensterebene, die Formularfelder bewusst ausspart) bleibt unverändert.

Die beiden Checkboxen (KI-Normalisierung, Ausrichtungsgitter) werden zu
Icon-Toggles im Header, weil sie Ansichtsschalter sind und nicht die
Auswahl der verglichenen Bilder betreffen.

### Header

`PageHeader` besitzt bereits einen `actions`-Slot; er wird genutzt statt
eines neuen Musters. Reihenfolge von links nach rechts: KI-Normalisierung
(Toggle), Ausrichtungsgitter (Toggle), Trennstrich, KI-Analyse (Accent),
Export.

Ansichtsschalter und Aktionen sind durch den Trennstrich optisch
getrennt, damit ein Toggle nicht mit einem auslösenden Button verwechselt
wird.

### Icons

Alle aus `lucide-react` (bereits Dependency, bisher nur in `ClientShell`
genutzt). Die Emoji 🥊 und 🔍/↻/☀ entfallen.

| Funktion | Icon |
|---|---|
| KI-Analyse | `Sparkles` |
| Export | `ImageDown` |
| KI-Normalisierung | `Scan` |
| Ausrichtungsgitter | `Grid3x3` |
| Side-by-Side | `Columns2` |
| Slider | `MoveHorizontal` |
| Zoom | `ZoomIn` |
| Neigung | `RotateCw` |
| Exposure | `Sun` |
| Zurücksetzen | `RotateCcw` |

## Zustände der Aktionen

| Situation | KI-Icon | Export-Icon |
|---|---|---|
| kein Ergebnis geladen | deaktiviert | deaktiviert |
| Ergebnis vorhanden | Accent, aktiv | aktiv |
| KI läuft | Spinner, daneben „Judge analysiert… {n}s" | unverändert aktiv |
| „All poses" | Accent mit Posenzahl als Badge | ausgeblendet |

Die Sekundenanzeige während der KI-Analyse bleibt erhalten (sie erklärt
lange Wartezeiten unter Serverlast) und steht künftig als kompakter Text
neben dem Icon statt unter einem Button.

Fehlermeldungen, die Hinweiszeile zu fehlenden normalisierten Bildern und
die Darstellung des KI-Ergebnisses bleiben unverändert.

## Barrierefreiheit

Da sämtliche Aktionen ihr Textlabel verlieren, gilt verbindlich:

- Jeder Icon-Button trägt ein `aria-label` und ein `title`
- Toggles tragen zusätzlich `aria-pressed`
- Das Popover ist per Tastatur erreichbar und mit Escape schließbar
- Sichtbarer Fokusring auf allen Icon-Buttons

## Out of Scope

- `usePanZoom`, die Export-Mathematik in `compareExport.ts` und das
  Export-Modal bleiben unangetastet
- Sticky-Verhalten der Steuerleiste beim Scrollen (als Aufsatz denkbar,
  hier bewusst nicht enthalten)
- Mobile-spezifische Optimierung (Bottom-Sheet, Touch-Targets)
- Einführung eines Komponenten-Test-Frameworks

## Verifikation

Für UI existiert in diesem Repo kein Komponenten-Test-Framework; eines
einzuführen wäre in diesem Schritt Scope Creep. Verifiziert wird:

- `npx tsc --noEmit` fehlerfrei
- `npm test` — die bestehenden `compareExport`-Tests bleiben grün
- Im Browser: Zoom per Mausrad, Pan per Ziehen, Doppelklick-Reset,
  alle drei Regler, Popover-Schließen per Escape und Außenklick,
  Tastaturbedienung, Modus-Umschaltung, Pose-Navigation über die Pfeile,
  KI-Analyse, Export — jeweils unverändert gegenüber heute
