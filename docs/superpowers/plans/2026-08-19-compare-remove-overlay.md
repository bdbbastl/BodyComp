# Compare Overlay Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the Overlay comparison mode from the Compare page (frontend-only), leaving Side-by-Side and Slider.

**Architecture:** Single-file edit to `frontend/src/pages/Compare.tsx` - narrow the `Mode` union type, drop the mode-toggle option, delete the overlay render block, delete the now-unused `opacity` state, delete the now-unused `OverlayPane` component.

**Tech Stack:** React, TypeScript.

---

### Task 1: Remove Overlay mode from Compare.tsx

**Files:**
- Modify: `frontend/src/pages/Compare.tsx`

- [ ] **Step 1: Narrow the `Mode` type**

At line 16, change:

```tsx
type Mode = "side-by-side" | "overlay" | "slider";
```

to:

```tsx
type Mode = "side-by-side" | "slider";
```

- [ ] **Step 2: Remove the `opacity` state**

Delete this line (currently line 33):

```tsx
  const [opacity, setOpacity] = useState(50);
```

- [ ] **Step 3: Remove "overlay" from the mode-toggle button list**

Find (currently lines 277-287):

```tsx
            {(["side-by-side", "overlay", "slider"] as Mode[]).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
                  mode === m ? "bg-accent text-slate-900" : "text-slate-400 hover:text-white"
                }`}
              >
                {m === "side-by-side" ? "Side-by-Side" : m === "overlay" ? "Overlay" : "Slider"}
              </button>
            ))}
```

Replace with:

```tsx
            {(["side-by-side", "slider"] as Mode[]).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
                  mode === m ? "bg-accent text-slate-900" : "text-slate-400 hover:text-white"
                }`}
              >
                {m === "side-by-side" ? "Side-by-Side" : "Slider"}
              </button>
            ))}
```

- [ ] **Step 4: Delete the overlay render block**

Find and delete the entire block (currently lines 394-440, starting with the comment/condition below and ending at the matching closing `)}`):

```tsx
      {!isAllPoses && result && mode === "overlay" && (
        <div className="space-y-4">
          {!normalize && (
            <p className="rounded-lg bg-yellow-500/10 px-3 py-2 text-sm text-yellow-400">
              Without AI normalization, camera distance/tilt usually won't match between the
              photos — enable the checkbox above for a meaningful overlay.
            </p>
          )}
          <OverlayPane
            key={`${result.photo_x.id}-${result.photo_y.id}`}
            srcX={resolveSrc(result.photo_x)}
            srcY={resolveSrc(result.photo_y)}
            filterX={filterFor(brightnessX)}
            filterY={filterFor(brightnessY)}
            opacity={opacity}
            altX={formatDate(dateX)}
            altY={formatDate(dateY)}
            showGrid={showGrid}
            gridLines={gridLines}
            onGridLineChange={updateGridLine}
          />

          <div className="mx-auto max-w-md rounded-xl border border-white/5 bg-surface p-4">
            <SliderControl
              icon="◐"
              label={`Opacity ${formatDate(dateY)}`}
              value={opacity}
              min={0}
              max={100}
              step={1}
              onChange={setOpacity}
              suffix="%"
            />
          </div>

          <div className="mx-auto grid max-w-md grid-cols-1 gap-x-6 gap-y-4 rounded-xl border border-white/5 bg-surface p-4 sm:grid-cols-2">
            <BrightnessSlider
              value={brightnessX}
              onChange={setBrightnessX}
            />
            <BrightnessSlider
              value={brightnessY}
              onChange={setBrightnessY}
            />
          </div>
        </div>
      )}

```

(Note the trailing blank line before `{!isAllPoses && result && mode === "slider" && (` - delete exactly through that blank line, no more, no less, so the slider block that follows keeps its normal one-blank-line separation from whatever precedes it.)

- [ ] **Step 5: Delete the `OverlayPane` component**

Find and delete the entire function (currently lines 787-864, from the doc comment through the closing `}`):

```tsx
/** Overlay-Variante: beide Bilder liegen übereinander und werden beim
 * Zoomen/Verschieben gemeinsam transformiert (sonst würden sie
 * auseinanderdriften). Neigung bleibt pro Bild eigenständig einstellbar
 * (Kamera-Tilt ist eine Eigenschaft der jeweiligen Aufnahme, kein
 * gemeinsamer Wert). */
function OverlayPane({
  srcX,
  srcY,
  filterX,
  filterY,
  opacity,
  altX,
  altY,
  showGrid,
  gridLines,
  onGridLineChange,
}: {
  srcX: string;
  srcY: string;
  filterX: string | undefined;
  filterY: string | undefined;
  opacity: number;
  altX: string;
  altY: string;
  showGrid?: boolean;
  gridLines?: number[];
  onGridLineChange?: (index: number, value: number) => void;
}) {
  const { scale, translate, containerRef, isDragging, reset, setScaleFromSlider } = usePanZoom();
  const [rotationX, setRotationX] = useState(0);
  const [rotationY, setRotationY] = useState(0);

  return (
    <div className="space-y-3">
      <div
        ref={containerRef}
        className="relative mx-auto aspect-[3/4] max-w-md overflow-hidden rounded-xl border border-white/5 bg-black/40"
        style={{ cursor: scale > 1 ? (isDragging ? "grabbing" : "grab") : "zoom-in" }}
        onDoubleClick={reset}
        title="Scroll to zoom, click+drag to pan while zoomed, double-click to reset"
      >
        <div className="absolute inset-0" style={transformStyle(translate, scale)}>
          <img
            src={srcX}
            alt={altX}
            draggable={false}
            className="h-full w-full object-cover"
            style={{ filter: filterX, transform: `rotate(${rotationX}deg)` }}
          />
        </div>
        <div className="absolute inset-0" style={transformStyle(translate, scale)}>
          <img
            src={srcY}
            alt={altY}
            draggable={false}
            className="h-full w-full object-cover"
            style={{ opacity: opacity / 100, filter: filterY, transform: `rotate(${rotationY}deg)` }}
          />
        </div>
        {showGrid && gridLines && onGridLineChange && (
          <AlignmentGridOverlay lines={gridLines} onChange={onGridLineChange} />
        )}
        {scale > 1 && (
          <span className="pointer-events-none absolute bottom-1 right-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-slate-200">
            {scale.toFixed(2)}×
          </span>
        )}
      </div>
      <div className="mx-auto max-w-md space-y-4 rounded-xl border border-white/5 bg-surface p-4">
        <ZoomSlider scale={scale} onChange={setScaleFromSlider} />
        <div className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2">
          <RotationSlider label={`Tilt ${altX}`} degrees={rotationX} onChange={setRotationX} />
          <RotationSlider label={`Tilt ${altY}`} degrees={rotationY} onChange={setRotationY} />
        </div>
      </div>
    </div>
  );
}

```

- [ ] **Step 6: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors. This is the primary safety net for this change - TypeScript will flag any leftover reference to `opacity`, `setOpacity`, `OverlayPane`, or the `"overlay"` literal that's no longer assignable to `Mode`.

- [ ] **Step 7: Manual verification**

Confirm by reading the file that:
- `SliderControl`, `ZoomSlider`, `RotationSlider`, `usePanZoom`, `transformStyle`, `AlignmentGridOverlay`, `BrightnessSlider` are all still referenced elsewhere in the file (they're shared, not overlay-specific) - if `npx tsc --noEmit` passes with no "unused import" issue (TypeScript doesn't error on unused imports by default, so this is a manual check), grep for each to confirm continued use:
  `grep -n "SliderControl\|ZoomSlider\|RotationSlider\|usePanZoom\|transformStyle\|AlignmentGridOverlay\|BrightnessSlider" frontend/src/pages/Compare.tsx`
  Each should still show at least one usage outside of an import line.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/Compare.tsx
git commit -m "feat: remove Overlay comparison mode from Compare page"
```

---

### Task 2: Finish branch

- [ ] **Step 1: Run frontend type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 2: Use the finishing-a-development-branch skill**

Invoke `superpowers:finishing-a-development-branch` to push per the user's standing "option 1" preference (this session works directly on `dev`).
