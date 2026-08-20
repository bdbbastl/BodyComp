# Compare-Export für Social Media — Design

## Ziel

"Export Comparison"-Button auf der Compare-Seite, der die aktuelle Vorher/Nachher-Gegenüberstellung als ein Bild herunterlädt — exakt im eingestellten Zustand (Zoom, Belichtung, Drehung, Pan), rein client-seitig, kein Server-Upload. Ersetzt/erweitert das frühere Konzept-Dokument mit denselben Namen; dieses Dokument ist die verbindliche Version.

## Umfang

- Export-Button für **beide Compare-Modi** (Side-by-Side und Slider).
- **Zwei Formate**: 1:1 (Instagram-Feed) und 4:3 (breiter). Auswahl über zwei Buttons/Tabs im Vorschau-Dialog (siehe unten).
- **Vorschau-Dialog vor dem Download**: Klick auf "Export Comparison" öffnet ein Modal mit dem fertig gerenderten Export-Bild (`<canvas>` bzw. daraus erzeugtes `<img>`), Format-Umschalter (1:1 / 4:3, live neu gerendert), und einem finalen "Download"-Button. Kein direkter Sofort-Download.
- **Trennlinie**: dünne weiße Linie (2-3px, leicht transparent) zwischen den beiden Fotos im Side-by-Side-Export. Im Slider-Export keine Trennlinie (bereits überlagert/Momentaufnahme des aktuellen Slider-Standes).
- **Wasserzeichen**: klein, halbtransparent, unten rechts im Export-Bild — Text "BodyComp Tracker" oder Logo-Icon, je nach Umsetzung in Task-Detail. Sichtbar aber dezent, verdeckt keine Bildinhalte.
- **Wasserzeichen-Regel** (bestätigt): Coach-Account mit aktivem bezahltem Abo → kein Wasserzeichen. Alle anderen Fälle → Wasserzeichen, **explizit auch Single-Account mit aktivem bezahltem Plan**.

## Architektur

**Problem:** Zoom (`scale`, `translate`), Rotation (`rotation`) und Pan werden aktuell rein lokal in `ZoomPane`/`SliderComparePane` gehalten (via `usePanZoom()`-Hook und lokalem `useState`) — `Compare.tsx` selbst kennt diese Werte nicht, nur `brightnessX`/`brightnessY` sind bereits nach oben gehoben.

**Lösung:** `ZoomPane` und `SliderComparePane` bekommen via `forwardRef` + `useImperativeHandle` eine imperative Methode `getExportState()`, die `{ scale, translateX, translateY, rotation }` zurückgibt (Brightness kommt weiterhin separat von den bereits vorhandenen `brightnessX`/`brightnessY`-Props/State in `Compare.tsx`). Kein Umbau der bestehenden Zoom/Pan/Rotation-Logik selbst nötig — nur ein zusätzlicher, rein lesender Zugriffspfad nach außen. `Compare.tsx` hält `refs` auf beide Panes und ruft beim Export-Klick `getExportState()` auf beiden auf.

**Canvas-Rendering:** Neue Funktion `renderComparisonToCanvas(...)` (neue Datei `frontend/src/utils/compareExport.ts`): erzeugt ein `<canvas>` in der gewählten Zielgröße (1:1 oder 4:3), zeichnet für jedes der beiden Fotos das `<img>`-Element mit `ctx.save()` → `ctx.translate/rotate/scale` entsprechend dem übergebenen Export-State → `ctx.filter = "brightness(...)"` (Canvas unterstützt `ctx.filter` mit denselben CSS-Filter-Strings, die die Live-Vorschau nutzt — kein Konvertierungsschritt nötig) → `ctx.drawImage(...)` → `ctx.restore()`. Trennlinie und Wasserzeichen werden danach als einfache Canvas-Zeichenoperationen (Linie, Text) obendrauf gezeichnet.

**Download:** `canvas.toBlob(...)` → `URL.createObjectURL(blob)` → `<a download="...">`-Klick, danach `URL.revokeObjectURL(...)`. Dateiname-Konvention: `bodycomp-compare-{ClientName}-{DateX}-vs-{DateY}.png` (Leerzeichen im Klientennamen durch `-` ersetzt).

## Sichtbarkeit / Wasserzeichen-Logik im Detail

`useCurrentUser()` liefert bereits `account_type`, `subscription_status`, `subscription_tier` — kein neuer Endpunkt nötig. Regel als reine Frontend-Funktion:

```
showWatermark = !(account_type === "coach" && ["active", "trialing"].includes(subscription_status))
```

(Trialing zählt als "aktiv bezahlt genug" für die Wasserzeichen-Befreiung, analog zur bestehenden Logik in `Dashboard.tsx`'s `UpgradeBanner`-Bedingung, die denselben `["trialing", "active"]`-Check verwendet.)

## Out of Scope

- Kein Server-seitiges Rendern/Speichern des Exports.
- Keine weiteren Formate über 1:1/4:3 hinaus in dieser Version.
- Kein Bearbeiten des Exports nach der Vorschau (z.B. Wasserzeichen-Position verschieben) - feste Platzierung.
