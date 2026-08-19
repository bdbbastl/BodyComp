# Compare-Seite: Overlay-Modus entfernen (Stufe 7b) — Design-Spec

**Datum:** 2026-08-19
**Status:** Genehmigt

## Kontext

Die Compare-Seite (`frontend/src/pages/Compare.tsx`) bietet drei Vergleichs-Modi: Side-by-Side, Overlay (beide Bilder mit einstellbarer Deckkraft übereinandergelegt) und Slider. Der Overlay-Modus wird als nicht sinnvoll genug eingeschätzt, um ihn zu behalten.

## Ziel

Overlay-Modus komplett entfernen, inklusive aller ausschließlich dafür genutzten Abhängigkeiten (State, Komponente, UI-Elemente). Side-by-Side und Slider bleiben unverändert. Rein frontend-seitige Änderung, keine Backend-Auswirkung (kein serverseitiger Zustand ist an den Modus gebunden).

## Umfang

Alles in `frontend/src/pages/Compare.tsx`:

1. `type Mode = "side-by-side" | "overlay" | "slider"` → `"side-by-side" | "slider"`.
2. Der 3-Wege-Modus-Umschalter (Zeilen ~277-289) verliert den "Overlay"-Button, bleibt als 2-Wege-Umschalter (Side-by-Side / Slider).
3. Der komplette Render-Block `{!isAllPoses && result && mode === "overlay" && (...)}` (Zeilen ~394-440) wird entfernt - enthält den Warnhinweis ohne KI-Normalisierung, die `<OverlayPane>`-Nutzung, und den Opacity-`SliderControl`.
4. `opacity`/`setOpacity`-State (Zeile ~33) wird entfernt - einziger Verwendungszweck war der entfernte Block.
5. Die `OverlayPane`-Funktionskomponente (ab Zeile ~792) wird komplett entfernt - keine anderen Aufrufer.

**Bleibt unverändert:** `AlignmentGridOverlay` (von Side-by-Side UND Slider genutzt, keine Overlay-Modus-Spezifik trotz ähnlichem Namen), `BrightnessSlider`, `SliderControl`-Import (weiterhin an anderer Stelle genutzt), die gesamte "Alle Posen"-Ansicht (nutzt gar keine Modus-Verzweigung).

## Out of Scope

- Keine Änderung an Side-by-Side oder Slider selbst.
- Keine Backend-Änderung.

## Testing-Ansatz

- Frontend: `npx tsc --noEmit` (fängt verwaiste Referenzen auf `opacity`/`OverlayPane`/`"overlay"` zuverlässig ab, da TypeScript den `Mode`-Union-Type nach der Änderung nicht mehr kennt).
- Manuell: Compare-Seite öffnen, nur noch 2 Modus-Buttons sichtbar, beide funktionieren wie zuvor, kein Rest-UI-Element vom Overlay-Modus sichtbar.
