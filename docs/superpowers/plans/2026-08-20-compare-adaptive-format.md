# Compare Adaptive Format & Big Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Compare's fixed 3:4 photo aspect ratio with one computed from the real dimensions of both compared photos (with manual preset override), extend zoom below 100%, add a fullscreen "Big Mode" preview, and give every control icon a visible text label.

**Architecture:** A new pure-function utility (`compareAspect.ts`) computes the shared box shape from both photos' real pixel dimensions. `ZoomPane`/`SliderComparePane` apply it via inline `aspectRatio` style instead of a hardcoded Tailwind class. Zoom's lower bound becomes configurable per `usePanZoom()` call so only Compare (not the unrelated `PhotoLightbox`) gets the extended range. The export canvas math is generalized to accept arbitrary target dimensions (not just the two fixed social-media formats), so a new `CompareBigMode` fullscreen component can reuse the *exact same* render function the export already uses — live preview, Big Mode, and export never diverge.

**Tech Stack:** React 18 + TypeScript + Tailwind + `lucide-react`. Verification via `npx tsc --noEmit`, `npm test` (node --test, pure logic only), and a manual browser pass — this repo has no component test framework.

**Spec:** `docs/superpowers/specs/2026-08-20-compare-adaptive-format-design.md`

**Note on data plumbing:** The spec calls for adding `width`/`height` to
the frontend `Photo` type. Verified while writing this plan — both
already exist (`frontend/src/types/index.ts:59-60`, predating this
work) and the comparisons endpoint already returns them via `PhotoOut`.
No task needed for this; `resolveAspectRatio` in Task 1 can use them
directly.

---

## File Structure

| File | Responsibility |
|---|---|
| `frontend/src/utils/compareAspect.ts` | **Create.** Pure functions: resolve a preset or auto-compute the shared box shape from two photos' real dimensions. |
| `frontend/src/components/CompareBigMode.tsx` | **Create.** Fullscreen preview overlay; reuses the same canvas render path as export. |
| `frontend/src/components/IconButton.tsx` | **Modify.** Adds optional visible text label next to the icon. |
| `frontend/src/hooks/usePanZoom.ts` | **Modify.** Zoom floor becomes configurable per call; adds `COMPARE_ZOOM_MIN`. |
| `frontend/src/components/ZoomSlider.tsx` | **Modify.** Adds optional `min` prop. |
| `frontend/src/components/PaneAdjustments.tsx` | **Modify.** Adds `zoomMin` prop, threads it to its internal `ZoomSlider`. |
| `frontend/src/components/CompareFilterBar.tsx` | **Modify.** Adds the Format preset chip group. |
| `frontend/src/utils/compareExport.ts` | **Modify.** Generalizes fixed export dimensions into arbitrary target dimensions. |
| `frontend/src/pages/Compare.tsx` | **Modify.** Wires aspect-ratio computation, zoom floor, Format presets, the shared render callback, and the Big Mode trigger/overlay. |

---

### Task 1: `compareAspect.ts` — aspect ratio computation

**Files:**
- Create: `frontend/src/utils/compareAspect.ts`
- Test: `frontend/src/utils/compareAspect.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/utils/compareAspect.test.ts`:

```typescript
// frontend/src/utils/compareAspect.test.ts
//
// Ausführen: node --test frontend/src/utils/compareAspect.test.ts

import assert from "node:assert/strict";
import { test } from "node:test";
import { ASPECT_PRESETS, computeAutoAspectRatio, resolveAspectRatio } from "./compareAspect.ts";

test("manuelle Presets werden unverändert zurückgegeben, nicht geklemmt", () => {
  assert.equal(resolveAspectRatio("3:4", undefined, undefined), 3 / 4);
  assert.equal(resolveAspectRatio("4:5", undefined, undefined), 4 / 5);
  assert.equal(resolveAspectRatio("9:16", undefined, undefined), 9 / 16);
});

test("auto: das hochkantigere (kleinere Seitenverhältnis) Foto gewinnt", () => {
  // X: 1000x2000 (0.5, sehr hochkant) - Y: 1000x1250 (0.8, eher quadratisch)
  const photoX = { width: 1000, height: 2000 };
  const photoY = { width: 1000, height: 1250 };
  // 0.5 liegt unter AUTO_MIN_RATIO (9/16 = 0.5625) - wird hochgeklemmt.
  assert.equal(computeAutoAspectRatio(photoX, photoY), ASPECT_PRESETS["9:16"]);
});

test("auto: Ergebnis innerhalb der Preset-Grenzen bleibt unverändert", () => {
  // X: 3:4 (0.75) - Y: 4:5 (0.8) -> min = 0.75, liegt zwischen 9:16 und 4:5.
  const photoX = { width: 900, height: 1200 };
  const photoY = { width: 800, height: 1000 };
  const result = computeAutoAspectRatio(photoX, photoY);
  assert.ok(Math.abs(result - 0.75) < 1e-9, `erwartet 0.75, war ${result}`);
});

test("auto: wird auf die breiteste erlaubte Form (4:5) geklemmt", () => {
  // Beide fast quadratisch (0.95/0.94) - über AUTO_MAX_RATIO (4/5 = 0.8) geklemmt.
  const photoX = { width: 950, height: 1000 };
  const photoY = { width: 940, height: 1000 };
  assert.equal(computeAutoAspectRatio(photoX, photoY), ASPECT_PRESETS["4:5"]);
});

test("auto: fehlende Fotomaße fallen auf 3:4 zurück", () => {
  const complete = { width: 900, height: 1200 };
  const missingWidth = { width: null, height: 1200 };
  const missingHeight = { width: 900, height: null };
  assert.equal(computeAutoAspectRatio(complete, missingWidth), 3 / 4);
  assert.equal(computeAutoAspectRatio(missingHeight, complete), 3 / 4);
  assert.equal(computeAutoAspectRatio(undefined, complete), 3 / 4);
});

test('resolveAspectRatio("auto", ...) entspricht computeAutoAspectRatio', () => {
  const photoX = { width: 1000, height: 1500 };
  const photoY = { width: 1000, height: 1400 };
  assert.equal(
    resolveAspectRatio("auto", photoX, photoY),
    computeAutoAspectRatio(photoX, photoY)
  );
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && node --test src/utils/compareAspect.test.ts`
Expected: FAIL — `Cannot find module './compareAspect.ts'` (file doesn't exist yet).

- [ ] **Step 3: Write the implementation**

Create `frontend/src/utils/compareAspect.ts`:

```typescript
// frontend/src/utils/compareAspect.ts
import type { Photo } from "../types";

/**
 * Seitenverhältnis der Compare-Container - siehe Design-Spec "Compare:
 * Adaptives Seitenverhältnis & Big Mode". "auto" berechnet die Form aus
 * den echten Pixelmaßen beider verglichener Fotos; die übrigen Werte
 * sind manuelle Presets, die die Automatik überschreiben.
 */
export type AspectPreset = "auto" | "3:4" | "4:5" | "9:16";

export const ASPECT_PRESETS: Record<Exclude<AspectPreset, "auto">, number> = {
  "3:4": 3 / 4,
  "4:5": 4 / 5,
  "9:16": 9 / 16,
};

// Heutiges Verhalten (fest 3:4), falls Fotomaße fehlen (alte, nicht
// nachgetragene Datensätze - siehe backend/app/services/folder_sync.py).
const FALLBACK_RATIO = 3 / 4;

// Die Auto-Berechnung wird nie extremer als die weiteste bzw. schmalste
// manuelle Preset-Option - verhindert, dass ein falsch rotiertes oder
// extrem verzerrtes Foto die Box absurd verformt.
const AUTO_MIN_RATIO = ASPECT_PRESETS["9:16"];
const AUTO_MAX_RATIO = ASPECT_PRESETS["4:5"];

type PhotoDimensions = Pick<Photo, "width" | "height">;

/** Seitenverhältnis (Breite/Höhe) beider Fotos, das kleinere gewinnt -
 * das hochkantigere Foto bestimmt die Form, das andere verliert
 * höchstens Rand links/rechts, nie Kopf oder Füße. Auf den erlaubten
 * Bereich geklemmt. Fehlen die Maße bei einem der beiden Fotos, gilt
 * der Fallback. */
export function computeAutoAspectRatio(
  photoX: PhotoDimensions | undefined,
  photoY: PhotoDimensions | undefined
): number {
  if (!photoX?.width || !photoX?.height || !photoY?.width || !photoY?.height) {
    return FALLBACK_RATIO;
  }
  const ratioX = photoX.width / photoX.height;
  const ratioY = photoY.width / photoY.height;
  const ratio = Math.min(ratioX, ratioY);
  return Math.min(AUTO_MAX_RATIO, Math.max(AUTO_MIN_RATIO, ratio));
}

/** Löst den gewählten Preset in ein konkretes Seitenverhältnis auf. Bei
 * einem manuellen Preset wird der feste Wert unverändert zurückgegeben
 * (eine bewusste Nutzerwahl wird nicht geklemmt); bei "auto" greift
 * computeAutoAspectRatio. */
export function resolveAspectRatio(
  preset: AspectPreset,
  photoX: PhotoDimensions | undefined,
  photoY: PhotoDimensions | undefined
): number {
  if (preset !== "auto") return ASPECT_PRESETS[preset];
  return computeAutoAspectRatio(photoX, photoY);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && node --test src/utils/compareAspect.test.ts`
Expected: `pass 6`, `fail 0`.

- [ ] **Step 5: Verify the whole suite and type-check**

Run: `cd frontend && npx tsc --noEmit && npm test`
Expected: no type errors; `pass 14` total (8 existing `compareExport` tests + 6 new).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/utils/compareAspect.ts frontend/src/utils/compareAspect.test.ts
git commit -m "feat: add compareAspect utility for dynamic photo box shape"
```

---

### Task 2: `IconButton` — visible label support

**Files:**
- Modify: `frontend/src/components/IconButton.tsx`

- [ ] **Step 1: Rewrite the component**

Replace the full contents of `frontend/src/components/IconButton.tsx` with:

```tsx
import type { LucideIcon } from "lucide-react";
import { Loader2 } from "lucide-react";

/**
 * Icon-Button, optional mit sichtbarem Text - genutzt im Compare-Header
 * (Ansichtsschalter + Aktionen) und in der Reglerleiste unter jedem Foto.
 *
 * `label` bleibt Pflicht-Prop und liefert aria-label/title (auch wenn
 * `showLabel` gesetzt ist - Screenreader lesen aria-label, nicht den
 * sichtbaren Textinhalt, und title bleibt als Tooltip-Fallback
 * nützlich). `visibleLabel` ist der KURZE Text, der bei showLabel
 * zusätzlich neben dem Icon erscheint - eigenständig von `label`, weil
 * der Tooltip ausführlicher sein darf als der Chip-Text.
 */
export function IconButton({
  icon: Icon,
  label,
  visibleLabel,
  showLabel = false,
  onClick,
  variant = "ghost",
  active = false,
  pending = false,
  disabled = false,
  toggle = false,
  dot = false,
  badge,
  size = "md",
}: {
  icon: LucideIcon;
  /** Pflicht - wird aria-label UND title. */
  label: string;
  /** Kurzer sichtbarer Text neben dem Icon, nur gerendert wenn showLabel. */
  visibleLabel?: string;
  showLabel?: boolean;
  onClick?: () => void;
  variant?: "ghost" | "accent";
  /** Toggle ist eingeschaltet bzw. Werkzeug ist ausgewählt. */
  active?: boolean;
  /** Zeigt einen Spinner und sperrt den Button. */
  pending?: boolean;
  disabled?: boolean;
  /** Setzt aria-pressed - nur für echte An/Aus-Schalter. */
  toggle?: boolean;
  /** Kleiner Akzentpunkt oben rechts: Wert weicht vom Standard ab. */
  dot?: boolean;
  /** Zahl oben rechts, z.B. Anzahl Posen bei "All poses". */
  badge?: number;
  size?: "sm" | "md";
}) {
  const glyph = size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4";
  const box = showLabel
    ? size === "sm"
      ? "h-8 gap-1.5 px-2.5"
      : "h-9 gap-2 px-3"
    : size === "sm"
      ? "h-8 w-8"
      : "h-9 w-9";
  const text = size === "sm" ? "text-xs" : "text-sm";

  const tone =
    variant === "accent"
      ? "border-accent bg-accent text-slate-900 hover:opacity-90"
      : active || pending
        ? "border-accent/40 bg-accent/10 text-accent hover:bg-accent/20"
        : "border-white/10 bg-white/5 text-slate-300 hover:bg-white/10 hover:text-white";

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || pending}
      aria-label={label}
      title={label}
      aria-pressed={toggle ? active : undefined}
      className={`relative inline-flex shrink-0 items-center justify-center rounded-lg border transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-35 ${box} ${tone}`}
    >
      {pending ? <Loader2 className={`${glyph} animate-spin`} /> : <Icon className={glyph} />}
      {showLabel && !pending && (
        <span className={`${text} font-medium whitespace-nowrap`}>{visibleLabel ?? label}</span>
      )}
      {dot && !pending && (
        <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full border-2 border-surface bg-accent" />
      )}
      {badge !== undefined && !pending && (
        <span className="absolute -right-1.5 -top-1.5 rounded-full border border-accent bg-background px-1 text-[9px] font-bold leading-4 text-accent">
          {badge}
        </span>
      )}
    </button>
  );
}
```

`showLabel` defaults to `false` — every existing call site (none pass it today) keeps its current square icon-only appearance until Task 12 explicitly turns it on.

- [ ] **Step 2: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/IconButton.tsx
git commit -m "feat: add visible label support to IconButton"
```

---

### Task 3: Configurable zoom floor — `usePanZoom` + `ZoomSlider`

**Files:**
- Modify: `frontend/src/hooks/usePanZoom.ts`
- Modify: `frontend/src/components/ZoomSlider.tsx`

- [ ] **Step 1: Make the zoom floor configurable in `usePanZoom`**

In `frontend/src/hooks/usePanZoom.ts`, find:

```typescript
export const ZOOM_MIN = 1;
export const ZOOM_MAX = 6;
```

Replace with:

```typescript
export const ZOOM_MIN = 1;
export const ZOOM_MAX = 6;
// Erweiterter unterer Zoom-Wert nur für die Compare-Seite (Live-
// Vorschau, Big Mode, Export) - erlaubt "Rauszoomen" für Fotos, die
// durch ihr Seitenverhältnis mehr Randbereich brauchen als die Box
// bietet. Andere usePanZoom-Nutzer (z.B. PhotoLightbox) übergeben
// keine Option und bleiben beim Standard ZOOM_MIN.
export const COMPARE_ZOOM_MIN = 0.5;
```

Find:

```typescript
export function usePanZoom() {
  const [scale, setScale] = useState(1);
```

Replace with:

```typescript
export function usePanZoom(options?: { zoomMin?: number }) {
  const zoomMin = options?.zoomMin ?? ZOOM_MIN;
  const [scale, setScale] = useState(1);
```

Find:

```typescript
  function applyZoomAtPoint(nextScaleRaw: number, px: number, py: number) {
    const nextScale = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, nextScaleRaw));
```

Replace with:

```typescript
  function applyZoomAtPoint(nextScaleRaw: number, px: number, py: number) {
    const nextScale = Math.min(ZOOM_MAX, Math.max(zoomMin, nextScaleRaw));
```

`reset()` is unchanged — it still resets to `scale = 1` (the neutral default), not to `zoomMin` (the floor). "Reset" means "back to normal", not "back to as far out as allowed".

- [ ] **Step 2: Add an optional `min` prop to `ZoomSlider`**

Replace the full contents of `frontend/src/components/ZoomSlider.tsx` with:

```tsx
import { ZOOM_MAX, ZOOM_MIN } from "../hooks/usePanZoom";
import { SliderControl } from "./SliderControl";

const STEP = 0.05;

/** Feinstufiger Zoom-Regler (zusätzlich zum Mausrad) - v.a. beim
 * Schieberegler-Vergleich und in der Timeline-Lightbox nützlich, um den
 * Ausschnitt exakt passend einzustellen. `min` optional, damit Compare
 * einen erweiterten unteren Wert (COMPARE_ZOOM_MIN) übergeben kann, ohne
 * PhotoLightbox (Default ZOOM_MIN) zu beeinflussen. */
export function ZoomSlider({
  scale,
  onChange,
  label = "Zoom",
  min = ZOOM_MIN,
}: {
  scale: number;
  onChange: (value: number) => void;
  label?: string;
  min?: number;
}) {
  return (
    <SliderControl
      label={label}
      value={scale}
      min={min}
      max={ZOOM_MAX}
      step={STEP}
      decimals={2}
      onChange={onChange}
      suffix="×"
    />
  );
}
```

- [ ] **Step 3: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors. `PhotoLightbox.tsx` calls `usePanZoom()` and `<ZoomSlider scale={scale} onChange={setScaleFromSlider} />` with no arguments in both cases — both keep working unchanged since the new params are optional with the original defaults.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/usePanZoom.ts frontend/src/components/ZoomSlider.tsx
git commit -m "feat: make zoom floor configurable per usePanZoom call"
```

---

### Task 4: `PaneAdjustments` — `zoomMin` prop

**Files:**
- Modify: `frontend/src/components/PaneAdjustments.tsx`

- [ ] **Step 1: Add the prop and thread it to the internal `ZoomSlider`**

Find:

```tsx
export function PaneAdjustments({
  scale,
  onScaleChange,
  rotation,
  onRotationChange,
  offset,
  onOffsetChange,
  brightness,
  onBrightnessChange,
  onReset,
}: {
  scale: number;
  onScaleChange: (value: number) => void;
  rotation: number;
  onRotationChange: (value: number) => void;
  offset?: Offset;
  onOffsetChange?: (offset: Offset) => void;
  brightness?: number;
  onBrightnessChange?: (value: number) => void;
  /** Setzt alle Werte dieses Panes auf Standard zurück. */
  onReset: () => void;
}) {
```

Replace with:

```tsx
export function PaneAdjustments({
  scale,
  onScaleChange,
  rotation,
  onRotationChange,
  offset,
  onOffsetChange,
  brightness,
  onBrightnessChange,
  zoomMin = ZOOM_MIN,
  onReset,
}: {
  scale: number;
  onScaleChange: (value: number) => void;
  rotation: number;
  onRotationChange: (value: number) => void;
  offset?: Offset;
  onOffsetChange?: (offset: Offset) => void;
  brightness?: number;
  onBrightnessChange?: (value: number) => void;
  /** Unterer Zoom-Grenzwert für den Zoom-Regler - siehe usePanZoom
   * COMPARE_ZOOM_MIN. Default ZOOM_MIN (Standardverhalten). */
  zoomMin?: number;
  /** Setzt alle Werte dieses Panes auf Standard zurück. */
  onReset: () => void;
}) {
```

Find:

```tsx
          {openTool === "zoom" && <ZoomSlider scale={scale} onChange={onScaleChange} />}
```

Replace with:

```tsx
          {openTool === "zoom" && <ZoomSlider scale={scale} onChange={onScaleChange} min={zoomMin} />}
```

The existing `zoomTouched = scale !== ZOOM_MIN;` line stays **unchanged** — "touched" means "differs from the neutral default of 1", which is unaffected by how far down the user is *allowed* to go.

- [ ] **Step 2: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/PaneAdjustments.tsx
git commit -m "feat: add zoomMin prop to PaneAdjustments"
```

---

### Task 5: `ZoomPane` & `SliderComparePane` — dynamic aspect ratio, zoom floor, letterbox background

**Files:**
- Modify: `frontend/src/pages/Compare.tsx`

- [ ] **Step 1: Import `COMPARE_ZOOM_MIN`**

Find:

```tsx
import { transformStyle, usePanZoom } from "../hooks/usePanZoom";
```

Replace with:

```tsx
import { COMPARE_ZOOM_MIN, transformStyle, usePanZoom } from "../hooks/usePanZoom";
```

- [ ] **Step 2: `ZoomPane` — add `aspectRatio` prop, apply zoom floor and background**

Find:

```tsx
const ZoomPane = forwardRef<ZoomPaneHandle, {
  src: string;
  alt: string;
  filter: string | undefined;
  caption?: ReactNode;
  brightness?: number;
  onBrightnessChange?: (value: number) => void;
  showBrightnessSlider?: boolean;
  showGrid?: boolean;
  gridLines?: number[];
  onGridLineChange?: (index: number, value: number) => void;
}>(function ZoomPane(
  {
    src,
    alt,
    filter,
    caption,
    brightness,
    onBrightnessChange,
    showBrightnessSlider = true,
    showGrid,
    gridLines,
    onGridLineChange,
  },
  ref
) {
  const { scale, translate, containerRef, isDragging, reset, setScaleFromSlider } = usePanZoom();
  const [rotation, setRotation] = useState(0);
```

Replace with:

```tsx
const ZoomPane = forwardRef<ZoomPaneHandle, {
  src: string;
  alt: string;
  filter: string | undefined;
  caption?: ReactNode;
  brightness?: number;
  onBrightnessChange?: (value: number) => void;
  showBrightnessSlider?: boolean;
  showGrid?: boolean;
  gridLines?: number[];
  onGridLineChange?: (index: number, value: number) => void;
  aspectRatio?: number;
}>(function ZoomPane(
  {
    src,
    alt,
    filter,
    caption,
    brightness,
    onBrightnessChange,
    showBrightnessSlider = true,
    showGrid,
    gridLines,
    onGridLineChange,
    aspectRatio = 3 / 4,
  },
  ref
) {
  const { scale, translate, containerRef, isDragging, reset, setScaleFromSlider } = usePanZoom({
    zoomMin: COMPARE_ZOOM_MIN,
  });
  const [rotation, setRotation] = useState(0);
```

Find:

```tsx
      <div
        ref={containerRef}
        className="relative aspect-[3/4] w-full overflow-hidden bg-black/40"
        style={{ cursor: scale > 1 ? (isDragging ? "grabbing" : "grab") : "zoom-in" }}
        onDoubleClick={reset}
        title="Scroll to zoom, click+drag to pan while zoomed, double-click to reset"
      >
```

Replace with:

```tsx
      <div
        ref={containerRef}
        className="relative w-full overflow-hidden bg-background"
        style={{ aspectRatio, cursor: scale > 1 ? (isDragging ? "grabbing" : "grab") : "zoom-in" }}
        onDoubleClick={reset}
        title="Scroll to zoom, click+drag to pan while zoomed, double-click to reset"
      >
```

Find (the zoom-level badge — extend it to also show when zoomed *out*, not only in):

```tsx
        {scale > 1 && (
          <span className="pointer-events-none absolute bottom-1 right-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-slate-200">
            {scale.toFixed(2)}×
          </span>
        )}
      </div>
      <div>
        {caption && <p className="px-3.5 pt-3 text-sm font-medium text-slate-300">{caption}</p>}
        <PaneAdjustments
          scale={scale}
          onScaleChange={setScaleFromSlider}
          rotation={rotation}
          onRotationChange={setRotation}
          brightness={showBrightnessSlider ? brightness : undefined}
          onBrightnessChange={showBrightnessSlider ? onBrightnessChange : undefined}
          onReset={() => {
            reset();
            setRotation(0);
            if (showBrightnessSlider && onBrightnessChange) onBrightnessChange(BRIGHTNESS_DEFAULT);
          }}
        />
      </div>
```

Replace with:

```tsx
        {scale !== 1 && (
          <span className="pointer-events-none absolute bottom-1 right-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-slate-200">
            {scale.toFixed(2)}×
          </span>
        )}
      </div>
      <div>
        {caption && <p className="px-3.5 pt-3 text-sm font-medium text-slate-300">{caption}</p>}
        <PaneAdjustments
          scale={scale}
          onScaleChange={setScaleFromSlider}
          rotation={rotation}
          onRotationChange={setRotation}
          brightness={showBrightnessSlider ? brightness : undefined}
          onBrightnessChange={showBrightnessSlider ? onBrightnessChange : undefined}
          zoomMin={COMPARE_ZOOM_MIN}
          onReset={() => {
            reset();
            setRotation(0);
            if (showBrightnessSlider && onBrightnessChange) onBrightnessChange(BRIGHTNESS_DEFAULT);
          }}
        />
      </div>
```

- [ ] **Step 3: `SliderComparePane` — same three changes**

Find:

```tsx
const SliderComparePane = forwardRef<SliderPaneHandle, {
  srcX: string;
  srcY: string;
  filterX: string | undefined;
  filterY: string | undefined;
  brightnessX: number;
  onBrightnessXChange: (value: number) => void;
  brightnessY: number;
  onBrightnessYChange: (value: number) => void;
  altX: string;
  altY: string;
  showGrid?: boolean;
  gridLines?: number[];
  onGridLineChange?: (index: number, value: number) => void;
}>(function SliderComparePane(
  {
    srcX,
    srcY,
    filterX,
    filterY,
    brightnessX,
    onBrightnessXChange,
    brightnessY,
    onBrightnessYChange,
    altX,
    altY,
    showGrid,
    gridLines,
    onGridLineChange,
  },
  ref
) {
  const { scale, translate, containerRef, isDragging, reset, setScaleFromSlider } = usePanZoom();
```

Replace with:

```tsx
const SliderComparePane = forwardRef<SliderPaneHandle, {
  srcX: string;
  srcY: string;
  filterX: string | undefined;
  filterY: string | undefined;
  brightnessX: number;
  onBrightnessXChange: (value: number) => void;
  brightnessY: number;
  onBrightnessYChange: (value: number) => void;
  altX: string;
  altY: string;
  showGrid?: boolean;
  gridLines?: number[];
  onGridLineChange?: (index: number, value: number) => void;
  aspectRatio?: number;
}>(function SliderComparePane(
  {
    srcX,
    srcY,
    filterX,
    filterY,
    brightnessX,
    onBrightnessXChange,
    brightnessY,
    onBrightnessYChange,
    altX,
    altY,
    showGrid,
    gridLines,
    onGridLineChange,
    aspectRatio = 3 / 4,
  },
  ref
) {
  const { scale, translate, containerRef, isDragging, reset, setScaleFromSlider } = usePanZoom({
    zoomMin: COMPARE_ZOOM_MIN,
  });
```

Find:

```tsx
      <div
        ref={containerRef}
        className="relative mx-auto aspect-[3/4] max-w-md overflow-hidden rounded-xl border border-white/5 bg-black/40 select-none"
        style={{ cursor: scale > 1 ? (isDragging ? "grabbing" : "grab") : "default" }}
        onDoubleClick={reset}
        title="Scroll to zoom, click+drag to pan while zoomed, drag the divider to compare"
      >
```

Replace with:

```tsx
      <div
        ref={containerRef}
        className="relative mx-auto max-w-md overflow-hidden rounded-xl border border-white/5 bg-background select-none"
        style={{ aspectRatio, cursor: scale > 1 ? (isDragging ? "grabbing" : "grab") : "default" }}
        onDoubleClick={reset}
        title="Scroll to zoom, click+drag to pan while zoomed, drag the divider to compare"
      >
```

Find:

```tsx
        {scale > 1 && (
          <span className="pointer-events-none absolute bottom-1 right-1 z-10 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-slate-200">
            {scale.toFixed(1)}×
          </span>
        )}
```

Replace with:

```tsx
        {scale !== 1 && (
          <span className="pointer-events-none absolute bottom-1 right-1 z-10 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-slate-200">
            {scale.toFixed(1)}×
          </span>
        )}
```

Find both `PaneAdjustments` calls inside `SliderComparePane`:

```tsx
            <PaneAdjustments
              scale={fineZoomX}
              onScaleChange={setFineZoomX}
              rotation={rotationX}
              onRotationChange={setRotationX}
              offset={offsetX}
              onOffsetChange={setOffsetX}
              brightness={brightnessX}
              onBrightnessChange={onBrightnessXChange}
              onReset={() => {
                setFineZoomX(1);
                setRotationX(0);
                setOffsetX({ x: 0, y: 0 });
                onBrightnessXChange(BRIGHTNESS_DEFAULT);
              }}
            />
```

Replace with:

```tsx
            <PaneAdjustments
              scale={fineZoomX}
              onScaleChange={setFineZoomX}
              rotation={rotationX}
              onRotationChange={setRotationX}
              offset={offsetX}
              onOffsetChange={setOffsetX}
              brightness={brightnessX}
              onBrightnessChange={onBrightnessXChange}
              zoomMin={COMPARE_ZOOM_MIN}
              onReset={() => {
                setFineZoomX(1);
                setRotationX(0);
                setOffsetX({ x: 0, y: 0 });
                onBrightnessXChange(BRIGHTNESS_DEFAULT);
              }}
            />
```

And:

```tsx
            <PaneAdjustments
              scale={fineZoomY}
              onScaleChange={setFineZoomY}
              rotation={rotationY}
              onRotationChange={setRotationY}
              offset={offsetY}
              onOffsetChange={setOffsetY}
              brightness={brightnessY}
              onBrightnessChange={onBrightnessYChange}
              onReset={() => {
                setFineZoomY(1);
                setRotationY(0);
                setOffsetY({ x: 0, y: 0 });
                onBrightnessYChange(BRIGHTNESS_DEFAULT);
              }}
            />
```

Replace with:

```tsx
            <PaneAdjustments
              scale={fineZoomY}
              onScaleChange={setFineZoomY}
              rotation={rotationY}
              onRotationChange={setRotationY}
              offset={offsetY}
              onOffsetChange={setOffsetY}
              brightness={brightnessY}
              onBrightnessChange={onBrightnessYChange}
              zoomMin={COMPARE_ZOOM_MIN}
              onReset={() => {
                setFineZoomY(1);
                setRotationY(0);
                setOffsetY({ x: 0, y: 0 });
                onBrightnessYChange(BRIGHTNESS_DEFAULT);
              }}
            />
```

`aspectRatio` defaults to `3 / 4` in both components, so this task compiles standalone — Task 6 makes `Compare.tsx` start passing real computed values, overriding the default.

- [ ] **Step 4: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Compare.tsx
git commit -m "feat: dynamic aspect ratio, extended zoom floor, letterbox background in compare panes"
```

---

### Task 6: Wire `formatPreset` + `resolveAspectRatio` into `Compare.tsx`

**Files:**
- Modify: `frontend/src/pages/Compare.tsx`

- [ ] **Step 1: Import the new utility**

Find:

```tsx
import { numberedPoseOptionLabel } from "../utils/poseLabel";
```

Replace with:

```tsx
import { numberedPoseOptionLabel } from "../utils/poseLabel";
import { resolveAspectRatio } from "../utils/compareAspect";
import type { AspectPreset } from "../utils/compareAspect";
```

- [ ] **Step 2: Add `formatPreset` state**

Find:

```tsx
  const [showGrid, setShowGrid] = useState(false);
  const [gridLines, setGridLines] = useState<number[]>([25, 50, 75]);
```

Replace with:

```tsx
  const [showGrid, setShowGrid] = useState(false);
  const [gridLines, setGridLines] = useState<number[]>([25, 50, 75]);
  // Bleibt bewusst über Posen-/Datumswechsel hinweg bestehen (siehe
  // Design-Spec) - der User hat ihn bewusst gewählt.
  const [formatPreset, setFormatPreset] = useState<AspectPreset>("auto");
```

- [ ] **Step 3: Compute the single-pose aspect ratio**

Find:

```tsx
  const poses = posesQuery.data ?? [];
  const result = comparisonQuery.data;
```

Replace with:

```tsx
  const poses = posesQuery.data ?? [];
  const result = comparisonQuery.data;
  const aspectRatio = resolveAspectRatio(formatPreset, result?.photo_x, result?.photo_y);
```

- [ ] **Step 4: Pass it to the side-by-side panes**

Find:

```tsx
          <ComparePane
            ref={paneXRef}
            label={formatDate(dateX)}
            src={resolveSrc(result.photo_x)}
            filter={filterFor(brightnessX)}
            brightness={brightnessX}
            onBrightnessChange={setBrightnessX}
            showGrid={showGrid}
            gridLines={gridLines}
            onGridLineChange={updateGridLine}
          />
          <ComparePane
            ref={paneYRef}
            label={formatDate(dateY)}
            src={resolveSrc(result.photo_y)}
            filter={filterFor(brightnessY)}
            brightness={brightnessY}
            onBrightnessChange={setBrightnessY}
            showGrid={showGrid}
            gridLines={gridLines}
            onGridLineChange={updateGridLine}
          />
```

Replace with:

```tsx
          <ComparePane
            ref={paneXRef}
            label={formatDate(dateX)}
            src={resolveSrc(result.photo_x)}
            filter={filterFor(brightnessX)}
            brightness={brightnessX}
            onBrightnessChange={setBrightnessX}
            aspectRatio={aspectRatio}
            showGrid={showGrid}
            gridLines={gridLines}
            onGridLineChange={updateGridLine}
          />
          <ComparePane
            ref={paneYRef}
            label={formatDate(dateY)}
            src={resolveSrc(result.photo_y)}
            filter={filterFor(brightnessY)}
            brightness={brightnessY}
            onBrightnessChange={setBrightnessY}
            aspectRatio={aspectRatio}
            showGrid={showGrid}
            gridLines={gridLines}
            onGridLineChange={updateGridLine}
          />
```

- [ ] **Step 5: Pass it to the slider pane**

Find:

```tsx
          <SliderComparePane
            ref={sliderPaneRef}
            key={`${result.photo_x.id}-${result.photo_y.id}`}
            srcX={resolveSrc(result.photo_x)}
            srcY={resolveSrc(result.photo_y)}
            filterX={filterFor(brightnessX)}
            filterY={filterFor(brightnessY)}
            brightnessX={brightnessX}
            onBrightnessXChange={setBrightnessX}
            brightnessY={brightnessY}
            onBrightnessYChange={setBrightnessY}
            altX={formatDate(dateX)}
            altY={formatDate(dateY)}
            showGrid={showGrid}
            gridLines={gridLines}
            onGridLineChange={updateGridLine}
          />
```

Replace with:

```tsx
          <SliderComparePane
            ref={sliderPaneRef}
            key={`${result.photo_x.id}-${result.photo_y.id}`}
            srcX={resolveSrc(result.photo_x)}
            srcY={resolveSrc(result.photo_y)}
            filterX={filterFor(brightnessX)}
            filterY={filterFor(brightnessY)}
            brightnessX={brightnessX}
            onBrightnessXChange={setBrightnessX}
            brightnessY={brightnessY}
            onBrightnessYChange={setBrightnessY}
            altX={formatDate(dateX)}
            altY={formatDate(dateY)}
            aspectRatio={aspectRatio}
            showGrid={showGrid}
            gridLines={gridLines}
            onGridLineChange={updateGridLine}
          />
```

- [ ] **Step 6: Per-row aspect ratio in "All poses"**

Find:

```tsx
          {allPosePairs.map(({ pose, photoX, photoY }) => (
            <section key={pose.id} className="space-y-2">
              <h2 className="text-base font-semibold text-white">
                {numberedPoseOptionLabel(poses.findIndex((p) => p.id === pose.id), pose.name)}
              </h2>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <ComparePane
                  label={formatDate(dateX)}
                  src={resolveSrc(photoX)}
                  filter={filterFor(brightnessX)}
                  brightness={brightnessX}
                  onBrightnessChange={setBrightnessX}
                  showBrightnessSlider={false}
                  showGrid={showGrid}
                  gridLines={gridLines}
                  onGridLineChange={updateGridLine}
                />
                <ComparePane
                  label={formatDate(dateY)}
                  src={resolveSrc(photoY)}
                  filter={filterFor(brightnessY)}
                  brightness={brightnessY}
                  onBrightnessChange={setBrightnessY}
                  showBrightnessSlider={false}
                  showGrid={showGrid}
                  gridLines={gridLines}
                  onGridLineChange={updateGridLine}
                />
              </div>
            </section>
          ))}
```

Replace with:

```tsx
          {allPosePairs.map(({ pose, photoX, photoY }) => {
            // Jede Pose hat ihr eigenes Fotopaar und damit potenziell
            // ihre eigene Auto-Form - der formatPreset selbst ist ein
            // einziger globaler Wert, nur das Auto-Ergebnis ist pro Zeile
            // unterschiedlich (siehe Design-Spec Abschnitt 3).
            const rowAspectRatio = resolveAspectRatio(formatPreset, photoX, photoY);
            return (
              <section key={pose.id} className="space-y-2">
                <h2 className="text-base font-semibold text-white">
                  {numberedPoseOptionLabel(poses.findIndex((p) => p.id === pose.id), pose.name)}
                </h2>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <ComparePane
                    label={formatDate(dateX)}
                    src={resolveSrc(photoX)}
                    filter={filterFor(brightnessX)}
                    brightness={brightnessX}
                    onBrightnessChange={setBrightnessX}
                    aspectRatio={rowAspectRatio}
                    showBrightnessSlider={false}
                    showGrid={showGrid}
                    gridLines={gridLines}
                    onGridLineChange={updateGridLine}
                  />
                  <ComparePane
                    label={formatDate(dateY)}
                    src={resolveSrc(photoY)}
                    filter={filterFor(brightnessY)}
                    brightness={brightnessY}
                    onBrightnessChange={setBrightnessY}
                    aspectRatio={rowAspectRatio}
                    showBrightnessSlider={false}
                    showGrid={showGrid}
                    gridLines={gridLines}
                    onGridLineChange={updateGridLine}
                  />
                </div>
              </section>
            );
          })}
```

- [ ] **Step 7: `ComparePane` — add the pass-through prop**

Find:

```tsx
const ComparePane = forwardRef<ZoomPaneHandle, {
  label: string;
  src: string;
  filter: string | undefined;
  brightness: number;
  onBrightnessChange: (value: number) => void;
  showBrightnessSlider?: boolean;
  showGrid?: boolean;
  gridLines?: number[];
  onGridLineChange?: (index: number, value: number) => void;
}>(function ComparePane(
  { label, src, filter, brightness, onBrightnessChange, showBrightnessSlider = true, showGrid, gridLines, onGridLineChange },
  ref
) {
  return (
    <figure className="overflow-hidden rounded-xl border border-white/5 bg-surface">
      <ZoomPane
        ref={ref}
        key={src}
        src={src}
        alt={label}
        filter={filter}
        caption={label}
        brightness={brightness}
        onBrightnessChange={onBrightnessChange}
        showBrightnessSlider={showBrightnessSlider}
        showGrid={showGrid}
        gridLines={gridLines}
        onGridLineChange={onGridLineChange}
      />
    </figure>
  );
});
```

Replace with:

```tsx
const ComparePane = forwardRef<ZoomPaneHandle, {
  label: string;
  src: string;
  filter: string | undefined;
  brightness: number;
  onBrightnessChange: (value: number) => void;
  aspectRatio?: number;
  showBrightnessSlider?: boolean;
  showGrid?: boolean;
  gridLines?: number[];
  onGridLineChange?: (index: number, value: number) => void;
}>(function ComparePane(
  {
    label,
    src,
    filter,
    brightness,
    onBrightnessChange,
    aspectRatio = 3 / 4,
    showBrightnessSlider = true,
    showGrid,
    gridLines,
    onGridLineChange,
  },
  ref
) {
  return (
    <figure className="overflow-hidden rounded-xl border border-white/5 bg-surface">
      <ZoomPane
        ref={ref}
        key={src}
        src={src}
        alt={label}
        filter={filter}
        caption={label}
        brightness={brightness}
        onBrightnessChange={onBrightnessChange}
        aspectRatio={aspectRatio}
        showBrightnessSlider={showBrightnessSlider}
        showGrid={showGrid}
        gridLines={gridLines}
        onGridLineChange={onGridLineChange}
      />
    </figure>
  );
});
```

- [ ] **Step 8: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/pages/Compare.tsx
git commit -m "feat: compute and wire dynamic aspect ratio through compare panes"
```

---

### Task 7: `CompareFilterBar` — Format preset chip group

**Files:**
- Modify: `frontend/src/components/CompareFilterBar.tsx`
- Modify: `frontend/src/pages/Compare.tsx`

- [ ] **Step 1: Import `AspectPreset` and add the two new props**

In `frontend/src/components/CompareFilterBar.tsx`, find:

```tsx
import { ChevronLeft, ChevronRight, Columns2, MoveHorizontal } from "lucide-react";
import type { Pose } from "../types";
import { numberedPoseOptionLabel } from "../utils/poseLabel";
```

Replace with:

```tsx
import { ChevronLeft, ChevronRight, Columns2, MoveHorizontal } from "lucide-react";
import type { Pose } from "../types";
import { numberedPoseOptionLabel } from "../utils/poseLabel";
import type { AspectPreset } from "../utils/compareAspect";
```

Find:

```tsx
  mode,
  onModeChange,
  showModeSwitch,
}: {
  poses: Pose[];
  poseValue: string;
  onPoseChange: (value: string) => void;
  onNavigate: (delta: number) => void;
  navigationDisabled: boolean;
  allPosesValue: string;
  dateX: string;
  dateY: string;
  onDateXChange: (value: string) => void;
  onDateYChange: (value: string) => void;
  availableDates: string[];
  datesDisabled: boolean;
  datePlaceholder: string;
  formatDate: (date: string) => string;
  mode: CompareMode;
  onModeChange: (mode: CompareMode) => void;
  showModeSwitch: boolean;
}) {
```

Replace with:

```tsx
  mode,
  onModeChange,
  showModeSwitch,
  formatPreset,
  onFormatPresetChange,
}: {
  poses: Pose[];
  poseValue: string;
  onPoseChange: (value: string) => void;
  onNavigate: (delta: number) => void;
  navigationDisabled: boolean;
  allPosesValue: string;
  dateX: string;
  dateY: string;
  onDateXChange: (value: string) => void;
  onDateYChange: (value: string) => void;
  availableDates: string[];
  datesDisabled: boolean;
  datePlaceholder: string;
  formatDate: (date: string) => string;
  mode: CompareMode;
  onModeChange: (mode: CompareMode) => void;
  showModeSwitch: boolean;
  formatPreset: AspectPreset;
  onFormatPresetChange: (preset: AspectPreset) => void;
}) {
```

- [ ] **Step 2: Render the chip group**

Find:

```tsx
      {showModeSwitch && (
        <div className="ml-auto flex gap-1 rounded-full bg-black/30 p-1">
```

Replace with:

```tsx
      <div>
        <div className={GROUP_LABEL_CLASS}>Format</div>
        <div className="flex gap-1 rounded-full bg-black/30 p-1">
          {(["auto", "3:4", "4:5", "9:16"] as AspectPreset[]).map((preset) => (
            <button
              key={preset}
              type="button"
              onClick={() => onFormatPresetChange(preset)}
              className={`rounded-full px-2.5 py-1.5 text-xs font-medium transition-colors ${
                formatPreset === preset ? "bg-accent text-slate-900" : "text-slate-400 hover:text-white"
              }`}
            >
              {preset === "auto" ? "Auto" : preset}
            </button>
          ))}
        </div>
      </div>

      {showModeSwitch && (
        <div className="ml-auto flex gap-1 rounded-full bg-black/30 p-1">
```

The Format group is **not** gated behind `showModeSwitch` — unlike the mode switch, the format choice still applies in "All poses" mode (each row gets its own auto-computed shape from the same global preset, per Task 6).

- [ ] **Step 3: Wire the new props in `Compare.tsx`**

Find:

```tsx
        mode={mode}
        onModeChange={setMode}
        showModeSwitch={!isAllPoses}
      />
```

Replace with:

```tsx
        mode={mode}
        onModeChange={setMode}
        showModeSwitch={!isAllPoses}
        formatPreset={formatPreset}
        onFormatPresetChange={setFormatPreset}
      />
```

- [ ] **Step 4: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/CompareFilterBar.tsx frontend/src/pages/Compare.tsx
git commit -m "feat: add format preset chip group to compare filter bar"
```

---

### Task 8: `compareExport.ts` — generalize target dimensions

**Files:**
- Modify: `frontend/src/utils/compareExport.ts`

- [ ] **Step 1: Add `TargetDimensions` and `resolveDimensions`**

Find:

```typescript
export type ExportAspect = "1:1" | "4:3";
```

Replace with:

```typescript
export type ExportAspect = "1:1" | "4:3";

export interface TargetDimensions {
  width: number;
  height: number;
}
```

Find:

```typescript
const EXPORT_DIMENSIONS: Record<ExportAspect, { width: number; height: number }> = {
  "1:1": { width: 1080, height: 1080 },
  "4:3": { width: 1200, height: 900 },
};

export function dimensionsFor(aspect: ExportAspect) {
  return EXPORT_DIMENSIONS[aspect];
}
```

Replace with:

```typescript
const EXPORT_DIMENSIONS: Record<ExportAspect, TargetDimensions> = {
  "1:1": { width: 1080, height: 1080 },
  "4:3": { width: 1200, height: 900 },
};

export function dimensionsFor(aspect: ExportAspect): TargetDimensions {
  return EXPORT_DIMENSIONS[aspect];
}

/** Verallgemeinerte Variante von dimensionsFor: nimmt entweder eines der
 * beiden benannten Export-Formate ODER beliebige Zielmaße direkt
 * entgegen. Genutzt von Big Mode, das keine feste Export-Form hat,
 * sondern die live gewählte Container-Form bildschirmfüllend zeigt -
 * derselbe Render-Pfad wie der Export, nur mit anderer Zielgröße. */
export function resolveDimensions(target: ExportAspect | TargetDimensions): TargetDimensions {
  if (typeof target === "string") return dimensionsFor(target);
  return target;
}
```

- [ ] **Step 2: Widen `renderSideBySideToCanvas` and `renderSliderToCanvas`**

Find:

```typescript
export function renderSideBySideToCanvas(
  canvas: HTMLCanvasElement,
  aspect: ExportAspect,
  imgX: HTMLImageElement,
  stateX: PaneExportState,
  imgY: HTMLImageElement,
  stateY: PaneExportState,
  showWatermark: boolean
): void {
  const { width, height } = dimensionsFor(aspect);
```

Replace with:

```typescript
export function renderSideBySideToCanvas(
  canvas: HTMLCanvasElement,
  target: ExportAspect | TargetDimensions,
  imgX: HTMLImageElement,
  stateX: PaneExportState,
  imgY: HTMLImageElement,
  stateY: PaneExportState,
  showWatermark: boolean
): void {
  const { width, height } = resolveDimensions(target);
```

Find:

```typescript
export function renderSliderToCanvas(
  canvas: HTMLCanvasElement,
  aspect: ExportAspect,
  imgX: HTMLImageElement,
  imgY: HTMLImageElement,
  state: SliderExportState,
  showWatermark: boolean
): void {
  const { width, height } = dimensionsFor(aspect);
```

Replace with:

```typescript
export function renderSliderToCanvas(
  canvas: HTMLCanvasElement,
  target: ExportAspect | TargetDimensions,
  imgX: HTMLImageElement,
  imgY: HTMLImageElement,
  state: SliderExportState,
  showWatermark: boolean
): void {
  const { width, height } = resolveDimensions(target);
```

This is backward-compatible: `ExportAspect` (a string literal type) is assignable to `ExportAspect | TargetDimensions`, so `Compare.tsx`'s existing `renderSideBySideToCanvas(canvas, aspect, ...)` call (where `aspect: ExportAspect`) keeps compiling unchanged.

- [ ] **Step 3: Verify**

Run: `cd frontend && npx tsc --noEmit && npm test`
Expected: no type errors; `pass 14`, `fail 0` (the existing 8 `compareExport` tests call `mapContainerToRegion`/`liveImagePlacement` directly, not the two render functions — this widening doesn't affect them).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/utils/compareExport.ts
git commit -m "feat: generalize compareExport render functions to accept arbitrary target dimensions"
```

---

### Task 9: Extract shared `renderComparisonToCanvas` in `Compare.tsx`

**Files:**
- Modify: `frontend/src/pages/Compare.tsx`

- [ ] **Step 1: Replace `handleExportRender` with a shared render function plus two thin wrappers**

Find:

```tsx
  const handleExportRender = useCallback(
    (canvas: HTMLCanvasElement, aspect: ExportAspect) => {
      if (!result) return;
      const imgX = new Image();
      const imgY = new Image();
      imgX.crossOrigin = "anonymous";
      imgY.crossOrigin = "anonymous";
      imgX.src = resolveSrc(result.photo_x);
      imgY.src = resolveSrc(result.photo_y);
      const draw = () => {
        if (!imgX.complete || !imgY.complete) return;
        const watermark = shouldShowWatermark(currentUser);
        if (mode === "side-by-side") {
          const stateX = paneXRef.current?.getExportState();
          const stateY = paneYRef.current?.getExportState();
          if (!stateX || !stateY) return;
          renderSideBySideToCanvas(
            canvas,
            aspect,
            imgX,
            { ...stateX, brightness: brightnessX },
            imgY,
            { ...stateY, brightness: brightnessY },
            watermark
          );
        } else {
          const sliderState = sliderPaneRef.current?.getExportState();
          if (!sliderState) return;
          renderSliderToCanvas(
            canvas,
            aspect,
            imgX,
            imgY,
            {
              ...sliderState,
              x: { ...sliderState.x, brightness: brightnessX },
              y: { ...sliderState.y, brightness: brightnessY },
            },
            watermark
          );
        }
      };
      imgX.onload = draw;
      imgY.onload = draw;
      draw();
    },
    [result, mode, brightnessX, brightnessY, currentUser]
  );
```

Replace with:

```tsx
  // Gemeinsamer Render-Pfad für Export UND Big Mode - beide sollen
  // exakt dieselbe Geometrie zeigen (siehe Design-Spec Leitprinzip).
  // Unterscheiden sich nur in der Zielgröße (fest vs. bildschirmfüllend)
  // und im Wasserzeichen (nur beim echten Download).
  const renderComparisonToCanvas = useCallback(
    (
      canvas: HTMLCanvasElement,
      target: ExportAspect | { width: number; height: number },
      showWatermark: boolean
    ) => {
      if (!result) return;
      const imgX = new Image();
      const imgY = new Image();
      imgX.crossOrigin = "anonymous";
      imgY.crossOrigin = "anonymous";
      imgX.src = resolveSrc(result.photo_x);
      imgY.src = resolveSrc(result.photo_y);
      const draw = () => {
        if (!imgX.complete || !imgY.complete) return;
        if (mode === "side-by-side") {
          const stateX = paneXRef.current?.getExportState();
          const stateY = paneYRef.current?.getExportState();
          if (!stateX || !stateY) return;
          renderSideBySideToCanvas(
            canvas,
            target,
            imgX,
            { ...stateX, brightness: brightnessX },
            imgY,
            { ...stateY, brightness: brightnessY },
            showWatermark
          );
        } else {
          const sliderState = sliderPaneRef.current?.getExportState();
          if (!sliderState) return;
          renderSliderToCanvas(
            canvas,
            target,
            imgX,
            imgY,
            {
              ...sliderState,
              x: { ...sliderState.x, brightness: brightnessX },
              y: { ...sliderState.y, brightness: brightnessY },
            },
            showWatermark
          );
        }
      };
      imgX.onload = draw;
      imgY.onload = draw;
      draw();
    },
    [result, mode, brightnessX, brightnessY]
  );

  const handleExportRender = useCallback(
    (canvas: HTMLCanvasElement, aspect: ExportAspect) => {
      renderComparisonToCanvas(canvas, aspect, shouldShowWatermark(currentUser));
    },
    [renderComparisonToCanvas, currentUser]
  );

  const handleBigModeRender = useCallback(
    (canvas: HTMLCanvasElement, dims: { width: number; height: number }) => {
      renderComparisonToCanvas(canvas, dims, false);
    },
    [renderComparisonToCanvas]
  );
```

`handleExportRender`'s external signature and behavior are byte-for-byte unchanged — `CompareExportModal`'s `render` prop still receives exactly the same function shape, watermark logic still runs on every export render.

- [ ] **Step 2: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Manual regression check**

Start the dev server through the preview tooling, open Compare with a real pose/date pair, click "Export Comparison" in the header, confirm the preview still renders and Download still works exactly as before this refactor.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Compare.tsx
git commit -m "refactor: extract shared renderComparisonToCanvas for export and big mode"
```

---

### Task 10: `CompareBigMode` — fullscreen preview component

**Files:**
- Create: `frontend/src/components/CompareBigMode.tsx`

- [ ] **Step 1: Write the component**

Create `frontend/src/components/CompareBigMode.tsx`:

```tsx
// frontend/src/components/CompareBigMode.tsx
import { useEffect, useRef } from "react";
import { ChevronLeft, ChevronRight, X } from "lucide-react";

/**
 * Vollbild-Vorschau des aktuellen Vergleichs - siehe Design-Spec
 * "Compare: Adaptives Seitenverhältnis & Big Mode". Zeigt den
 * AKTUELLEN Stand (Zoom/Pan/Neigung/Belichtung/Format), verändert
 * nichts selbst; einzige Interaktion ist die Posen-Navigation über die
 * Pfeile hier oder die globale Pfeiltasten-Steuerung (siehe goToPose in
 * Compare.tsx - läuft unabhängig weiter, Big Mode fängt keinen Fokus).
 *
 * `render` ist derselbe Render-Pfad wie der Export (siehe
 * Compare.tsx renderComparisonToCanvas), nur mit showWatermark=false
 * und bildschirmfüllenden statt fest vorgegebenen Zielmaßen - Live-
 * Vorschau, Big Mode und Export zeigen dadurch garantiert dieselbe
 * Geometrie.
 */
export function CompareBigMode({
  aspectRatio,
  render,
  poseLabel,
  onNavigate,
  onClose,
}: {
  aspectRatio: number;
  render: (canvas: HTMLCanvasElement, dims: { width: number; height: number }) => void;
  poseLabel: string;
  onNavigate: (delta: number) => void;
  onClose: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  useEffect(() => {
    function draw() {
      const canvas = canvasRef.current;
      if (!canvas) return;
      // Größtmögliche Fläche innerhalb des verfügbaren Bereichs
      // (Viewport abzüglich Kopfleiste + Rand), die aspectRatio exakt
      // einhält - analog zu object-fit: contain, aber als konkrete
      // Canvas-Auflösung statt CSS-Skalierung, damit das Ergebnis nicht
      // unscharf hochskaliert wird.
      const availableWidth = window.innerWidth - 64;
      const availableHeight = window.innerHeight - 96;
      let width = availableWidth;
      let height = width / aspectRatio;
      if (height > availableHeight) {
        height = availableHeight;
        width = height * aspectRatio;
      }
      render(canvas, { width: Math.round(width), height: Math.round(height) });
    }
    draw();
    window.addEventListener("resize", draw);
    return () => window.removeEventListener("resize", draw);
  }, [render, aspectRatio]);

  return (
    <div className="fixed inset-0 z-[95] flex flex-col items-center bg-black/90 p-4">
      <div className="mb-3 flex w-full max-w-4xl items-center justify-between">
        <button
          type="button"
          onClick={() => onNavigate(-1)}
          aria-label="Previous pose"
          className="flex h-10 w-10 items-center justify-center rounded-full bg-white/10 text-white hover:bg-white/20"
        >
          <ChevronLeft className="h-5 w-5" />
        </button>
        <span className="text-sm font-medium text-slate-200">{poseLabel}</span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onNavigate(1)}
            aria-label="Next pose"
            className="flex h-10 w-10 items-center justify-center rounded-full bg-white/10 text-white hover:bg-white/20"
          >
            <ChevronRight className="h-5 w-5" />
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="flex h-10 w-10 items-center justify-center rounded-full bg-white/10 text-white hover:bg-white/20"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
      </div>
      <canvas ref={canvasRef} className="max-h-full max-w-full rounded-xl" />
    </div>
  );
}
```

- [ ] **Step 2: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors. This component isn't wired into `Compare.tsx` yet (Task 11) — it's fine that nothing renders it after this task.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/CompareBigMode.tsx
git commit -m "feat: add CompareBigMode fullscreen preview component"
```

---

### Task 11: Wire Big Mode into `Compare.tsx`

**Files:**
- Modify: `frontend/src/pages/Compare.tsx`

- [ ] **Step 1: Add imports**

Find:

```tsx
import { Grid3x3, ImageDown, Scan, Sparkles } from "lucide-react";
import { IconButton } from "../components/IconButton";
```

Replace with:

```tsx
import { Grid3x3, ImageDown, Maximize2, Scan, Sparkles } from "lucide-react";
import { IconButton } from "../components/IconButton";
import { CompareBigMode } from "../components/CompareBigMode";
```

- [ ] **Step 2: Add `showBigMode` state and the current-pose label**

Find:

```tsx
  const [showExportModal, setShowExportModal] = useState(false);
  const { data: currentUser } = useCurrentUser();
```

Replace with:

```tsx
  const [showExportModal, setShowExportModal] = useState(false);
  const [showBigMode, setShowBigMode] = useState(false);
  const { data: currentUser } = useCurrentUser();
```

Find:

```tsx
  const poses = posesQuery.data ?? [];
  const result = comparisonQuery.data;
  const aspectRatio = resolveAspectRatio(formatPreset, result?.photo_x, result?.photo_y);
```

Replace with:

```tsx
  const poses = posesQuery.data ?? [];
  const result = comparisonQuery.data;
  const aspectRatio = resolveAspectRatio(formatPreset, result?.photo_x, result?.photo_y);
  const currentPoseIndex = poses.findIndex((p) => p.id === poseSelection);
  const currentPoseLabel =
    currentPoseIndex >= 0 ? numberedPoseOptionLabel(currentPoseIndex, poses[currentPoseIndex].name) : "";
```

- [ ] **Step 3: Add the trigger icon**

Find:

```tsx
            <IconButton
              icon={Grid3x3}
              label="Ausrichtungsgitter"
              toggle
              active={showGrid}
              onClick={() => setShowGrid((v) => !v)}
            />
            <span className="mx-1 h-6 w-px bg-white/10" aria-hidden="true" />
```

Replace with:

```tsx
            <IconButton
              icon={Grid3x3}
              label="Ausrichtungsgitter"
              toggle
              active={showGrid}
              onClick={() => setShowGrid((v) => !v)}
            />
            {!isAllPoses && (
              <IconButton
                icon={Maximize2}
                label="Groß anzeigen"
                disabled={!result}
                onClick={() => setShowBigMode(true)}
              />
            )}
            <span className="mx-1 h-6 w-px bg-white/10" aria-hidden="true" />
```

- [ ] **Step 4: Render the overlay**

Find:

```tsx
      {showExportModal && result && (
        <CompareExportModal
          onClose={() => setShowExportModal(false)}
          filename={exportFilename(`client-${clientIdNum}`, dateX, dateY)}
          render={handleExportRender}
        />
      )}
    </div>
  );
}
```

Replace with:

```tsx
      {showExportModal && result && (
        <CompareExportModal
          onClose={() => setShowExportModal(false)}
          filename={exportFilename(`client-${clientIdNum}`, dateX, dateY)}
          render={handleExportRender}
        />
      )}

      {showBigMode && !isAllPoses && result && (
        <CompareBigMode
          aspectRatio={aspectRatio}
          render={handleBigModeRender}
          poseLabel={currentPoseLabel}
          onNavigate={goToPose}
          onClose={() => setShowBigMode(false)}
        />
      )}
    </div>
  );
}
```

If the user arrows to a pose with no photo for the current date pair while Big Mode is open, `result` becomes `undefined` and Big Mode closes automatically (the guard above unmounts it) — a reasonable, non-broken fallback; no extra state handling needed.

- [ ] **Step 5: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Manual check**

Start the dev server, open Compare with a real pose/date pair (side-by-side mode), click the new "Groß anzeigen" icon — the overlay should fill the screen showing the same crop as the small preview. Press → to switch pose while it's open; the image should update. Press Escape to close. Repeat in slider mode. Confirm the icon is entirely absent in "All poses" mode.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Compare.tsx
git commit -m "feat: wire Big Mode trigger and overlay into Compare page"
```

---

### Task 12: Apply visible labels to all icon buttons

**Files:**
- Modify: `frontend/src/pages/Compare.tsx`
- Modify: `frontend/src/components/PaneAdjustments.tsx`

- [ ] **Step 1: Header actions in `Compare.tsx`**

Find:

```tsx
            <IconButton
              icon={Scan}
              label="KI-Normalisierung (Ausrichtung & Skalierung)"
              toggle
              active={normalize}
              onClick={() => setNormalize((v) => !v)}
            />
            <IconButton
              icon={Grid3x3}
              label="Ausrichtungsgitter"
              toggle
              active={showGrid}
              onClick={() => setShowGrid((v) => !v)}
            />
            {!isAllPoses && (
              <IconButton
                icon={Maximize2}
                label="Groß anzeigen"
                disabled={!result}
                onClick={() => setShowBigMode(true)}
              />
            )}
            <span className="mx-1 h-6 w-px bg-white/10" aria-hidden="true" />
            <IconButton
              icon={Sparkles}
              label={
                isAllPoses
                  ? `KI-Gesamtanalyse (${allPosePairs.length} Posen)`
                  : "KI-Analyse (Judge-Bewertung)"
              }
              variant="accent"
              pending={activeAiMutation.isPending}
              disabled={!canAnalyze}
              badge={isAllPoses && allPosePairs.length > 0 ? allPosePairs.length : undefined}
              onClick={() => {
                show("Judge analyzing…");
                activeAiMutation.mutate();
              }}
            />
            {!isAllPoses && (
              <IconButton
                icon={ImageDown}
                label="Vergleich exportieren"
                disabled={!result}
                onClick={() => setShowExportModal(true)}
              />
            )}
```

Replace with:

```tsx
            <IconButton
              icon={Scan}
              label="KI-Normalisierung (Ausrichtung & Skalierung)"
              visibleLabel="KI-Norm."
              showLabel
              toggle
              active={normalize}
              onClick={() => setNormalize((v) => !v)}
            />
            <IconButton
              icon={Grid3x3}
              label="Ausrichtungsgitter"
              visibleLabel="Gitter"
              showLabel
              toggle
              active={showGrid}
              onClick={() => setShowGrid((v) => !v)}
            />
            {!isAllPoses && (
              <IconButton
                icon={Maximize2}
                label="Groß anzeigen"
                visibleLabel="Groß"
                showLabel
                disabled={!result}
                onClick={() => setShowBigMode(true)}
              />
            )}
            <span className="mx-1 h-6 w-px bg-white/10" aria-hidden="true" />
            <IconButton
              icon={Sparkles}
              label={
                isAllPoses
                  ? `KI-Gesamtanalyse (${allPosePairs.length} Posen)`
                  : "KI-Analyse (Judge-Bewertung)"
              }
              visibleLabel="KI-Analyse"
              showLabel
              variant="accent"
              pending={activeAiMutation.isPending}
              disabled={!canAnalyze}
              badge={isAllPoses && allPosePairs.length > 0 ? allPosePairs.length : undefined}
              onClick={() => {
                show("Judge analyzing…");
                activeAiMutation.mutate();
              }}
            />
            {!isAllPoses && (
              <IconButton
                icon={ImageDown}
                label="Vergleich exportieren"
                visibleLabel="Export"
                showLabel
                disabled={!result}
                onClick={() => setShowExportModal(true)}
              />
            )}
```

- [ ] **Step 2: Icon row in `PaneAdjustments.tsx`**

Find:

```tsx
  return (
    <div ref={rootRef} className="relative p-3">
      <div className="flex items-center gap-2">
        <IconButton
          icon={ZoomIn}
          label="Zoom"
          size="sm"
          active={openTool === "zoom"}
          dot={zoomTouched}
          onClick={() => toggle("zoom")}
        />
        <IconButton
          icon={RotateCw}
          label="Neigung"
          size="sm"
          active={openTool === "rotation"}
          dot={rotationTouched}
          onClick={() => toggle("rotation")}
        />
        {hasPosition && (
          <IconButton
            icon={Move}
            label="Position"
            size="sm"
            active={openTool === "position"}
            dot={positionTouched}
            onClick={() => toggle("position")}
          />
        )}
        {hasExposure && (
          <IconButton
            icon={Sun}
            label="Exposure"
            size="sm"
            active={openTool === "exposure"}
            dot={exposureTouched}
            onClick={() => toggle("exposure")}
          />
        )}
        <div className="ml-auto">
          <IconButton
            icon={RotateCcw}
            label="Alles zurücksetzen"
            size="sm"
            disabled={!anyTouched}
            onClick={() => {
              onReset();
              setOpenTool(null);
            }}
          />
        </div>
      </div>
```

Replace with:

```tsx
  return (
    <div ref={rootRef} className="relative p-3">
      <div className="flex flex-wrap items-center gap-2">
        <IconButton
          icon={ZoomIn}
          label="Zoom"
          visibleLabel="Zoom"
          showLabel
          size="sm"
          active={openTool === "zoom"}
          dot={zoomTouched}
          onClick={() => toggle("zoom")}
        />
        <IconButton
          icon={RotateCw}
          label="Neigung"
          visibleLabel="Neigung"
          showLabel
          size="sm"
          active={openTool === "rotation"}
          dot={rotationTouched}
          onClick={() => toggle("rotation")}
        />
        {hasPosition && (
          <IconButton
            icon={Move}
            label="Position"
            visibleLabel="Position"
            showLabel
            size="sm"
            active={openTool === "position"}
            dot={positionTouched}
            onClick={() => toggle("position")}
          />
        )}
        {hasExposure && (
          <IconButton
            icon={Sun}
            label="Exposure"
            visibleLabel="Exposure"
            showLabel
            size="sm"
            active={openTool === "exposure"}
            dot={exposureTouched}
            onClick={() => toggle("exposure")}
          />
        )}
        <div className="ml-auto">
          <IconButton
            icon={RotateCcw}
            label="Alles zurücksetzen"
            visibleLabel="Reset"
            showLabel
            size="sm"
            disabled={!anyTouched}
            onClick={() => {
              onReset();
              setOpenTool(null);
            }}
          />
        </div>
      </div>
```

`flex-wrap` on the row (was `flex items-center gap-2`) lets the up-to-five text+icon chips wrap onto a second line instead of overflowing when a pane column is narrow (see Design-Spec Abschnitt 6).

- [ ] **Step 3: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Manual check**

Start the dev server, open Compare with a real pose/date pair. Confirm every header icon and every pane adjustment icon now shows a short text label next to it, and that the pane row wraps cleanly rather than overflowing on a narrow column (resize the browser window narrower to check).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Compare.tsx frontend/src/components/PaneAdjustments.tsx
git commit -m "feat: show visible text labels on all compare control icons"
```

---

### Task 13: Full verification and finish

- [ ] **Step 1: Type-check, build, test**

Run: `cd frontend && npx tsc --noEmit && npx vite build && npm test`
Expected: no type errors, build succeeds, `pass 14`, `fail 0`.

- [ ] **Step 2: Manual regression pass — Side-by-Side**

Open Compare, pick a pose/date pair with two photos of noticeably different natural aspect ratios if available (or any pair otherwise):

- Auto format shows both photos without cutting off heads/feet
- Format chips (Auto/3:4/4:5/9:16) switch the box shape visibly and immediately
- Zoom slider and mouse wheel now go down to 0.5× with visible letterbox background (`bg-background`, not the old translucent black)
- The zoom-level badge now also appears when zoomed *out* (below 1×), not only when zoomed in
- Double-click still resets zoom/pan to 1× / centered
- Big Mode ("Groß anzeigen" icon) opens fullscreen showing the identical crop as the small preview
- Arrow keys switch pose while Big Mode is open; Escape and the × button close it
- Export download shows exactly the same crop as Big Mode and the live preview
- Every header icon and every pane adjustment icon shows a short visible text label

- [ ] **Step 3: Manual regression pass — Slider mode and "All poses"**

- Slider mode: shared zoom slider still moves both images; per-image zoom/rotation/position/exposure still work via their icon rows; reset still isolates per-image values from the shared pan/zoom
- "All poses": each pose row shows its own auto-computed shape independent of the others; the "Groß anzeigen" icon is completely absent; the AI icon still shows the pose-count badge; Format chips still work and affect every row

- [ ] **Step 4: Use superpowers:finishing-a-development-branch**

Follow that skill to present merge/PR/keep/discard options and complete the branch.
