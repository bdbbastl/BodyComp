# Compare Export Social Media Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an "Export Comparison" button to the Compare page that downloads the current side-by-side or slider comparison as a single image (1:1 or 4:3), reproducing the exact zoom/pan/rotation/brightness state, with a watermark for non-paying-coach accounts.

**Architecture:** `ZoomPane` and `SliderComparePane` expose their current transform state via `forwardRef`/`useImperativeHandle` (read-only, no change to existing zoom/pan/rotation logic). A new pure-function module `frontend/src/utils/compareExport.ts` renders that state onto an offscreen `<canvas>` (divider line, watermark). A new `ExportPreviewModal` component shows the rendered result with a format switch (1:1/4:3) and a final download button.

**Tech Stack:** React + TypeScript + Canvas API (frontend only, no backend changes). No frontend test framework in this repo — verification via `npx tsc --noEmit` and manual browser check.

---

### Task 1: Canvas export utility (pure functions)

**Files:**
- Create: `frontend/src/utils/compareExport.ts`

- [ ] **Step 1: Write the export state types and the watermark-visibility function**

```typescript
// frontend/src/utils/compareExport.ts
import type { CurrentUser } from "../api/client";

export interface PaneExportState {
  scale: number;
  translateX: number;
  translateY: number;
  rotation: number;
  brightness: number;
}

export interface SliderExportState {
  scale: number;
  translateX: number;
  translateY: number;
  dividerPct: number;
  x: { offsetX: number; offsetY: number; fineZoom: number; rotation: number; brightness: number };
  y: { offsetX: number; offsetY: number; fineZoom: number; rotation: number; brightness: number };
}

export type ExportAspect = "1:1" | "4:3";

/** Wasserzeichen-Regel - siehe Design-Spec "Compare-Export für Social
 * Media" Abschnitt "Sichtbarkeit / Wasserzeichen-Logik im Detail".
 * Nur zahlende Coaches sind befreit - Single-Accounts (auch mit
 * aktivem Plan) bekommen immer ein Wasserzeichen. */
export function shouldShowWatermark(user: Pick<CurrentUser, "account_type" | "subscription_status"> | undefined): boolean {
  if (!user) return true;
  const isPayingCoach =
    user.account_type === "coach" && ["active", "trialing"].includes(user.subscription_status ?? "");
  return !isPayingCoach;
}

export function exportFilename(clientName: string, dateX: string, dateY: string): string {
  const safeName = clientName.trim().replace(/\s+/g, "-");
  return `bodycomp-compare-${safeName}-${dateX}-vs-${dateY}.png`;
}
```

- [ ] **Step 2: Add the canvas dimension helper**

Append to the same file:

```typescript
const EXPORT_DIMENSIONS: Record<ExportAspect, { width: number; height: number }> = {
  "1:1": { width: 1080, height: 1080 },
  "4:3": { width: 1200, height: 900 },
};

export function dimensionsFor(aspect: ExportAspect) {
  return EXPORT_DIMENSIONS[aspect];
}
```

- [ ] **Step 3: Write the side-by-side canvas renderer**

Append to the same file:

```typescript
/** Zeichnet ein einzelnes Foto mit seinem aktuellen Zoom/Pan/Rotation/
 * Belichtung-Zustand in eine rechteckige Zielregion des Canvas -
 * gemeinsam genutzt von renderSideBySide und renderSlider. slotWidth/
 * slotHeight sind die Zielgröße der Region (z.B. eine Bildhälfte),
 * (offsetXPx, offsetYPx) die obere linke Ecke der Region auf dem
 * Gesamt-Canvas. */
function drawPhotoIntoRegion(
  ctx: CanvasRenderingContext2D,
  img: HTMLImageElement,
  region: { x: number; y: number; width: number; height: number },
  state: { scale: number; translateX: number; translateY: number; rotation: number; brightness: number }
): void {
  ctx.save();
  ctx.beginPath();
  ctx.rect(region.x, region.y, region.width, region.height);
  ctx.clip();

  ctx.filter = state.brightness === 100 ? "none" : `brightness(${state.brightness}%)`;

  // object-cover-Skalierung: Bild füllt die Zielregion vollständig aus,
  // überschüssige Ränder werden vom Clip oben abgeschnitten.
  const coverScale = Math.max(region.width / img.naturalWidth, region.height / img.naturalHeight);
  const drawWidth = img.naturalWidth * coverScale * state.scale;
  const drawHeight = img.naturalHeight * coverScale * state.scale;
  const centerX = region.x + region.width / 2 + state.translateX;
  const centerY = region.y + region.height / 2 + state.translateY;

  ctx.translate(centerX, centerY);
  ctx.rotate((state.rotation * Math.PI) / 180);
  ctx.drawImage(img, -drawWidth / 2, -drawHeight / 2, drawWidth, drawHeight);

  ctx.restore();
}

function drawDivider(ctx: CanvasRenderingContext2D, x: number, canvasHeight: number): void {
  ctx.save();
  ctx.strokeStyle = "rgba(255, 255, 255, 0.85)";
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(x, 0);
  ctx.lineTo(x, canvasHeight);
  ctx.stroke();
  ctx.restore();
}

function drawWatermark(ctx: CanvasRenderingContext2D, canvasWidth: number, canvasHeight: number): void {
  ctx.save();
  ctx.font = "600 20px sans-serif";
  ctx.fillStyle = "rgba(255, 255, 255, 0.55)";
  ctx.textAlign = "right";
  ctx.textBaseline = "bottom";
  ctx.fillText("BodyComp Tracker", canvasWidth - 16, canvasHeight - 14);
  ctx.restore();
}

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
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  ctx.fillStyle = "#0b0f14";
  ctx.fillRect(0, 0, width, height);

  const halfWidth = width / 2;
  drawPhotoIntoRegion(ctx, imgX, { x: 0, y: 0, width: halfWidth, height }, stateX);
  drawPhotoIntoRegion(ctx, imgY, { x: halfWidth, y: 0, width: halfWidth, height }, stateY);
  drawDivider(ctx, halfWidth, height);

  if (showWatermark) drawWatermark(ctx, width, height);
}

export function renderSliderToCanvas(
  canvas: HTMLCanvasElement,
  aspect: ExportAspect,
  imgX: HTMLImageElement,
  imgY: HTMLImageElement,
  state: SliderExportState,
  showWatermark: boolean
): void {
  const { width, height } = dimensionsFor(aspect);
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  ctx.fillStyle = "#0b0f14";
  ctx.fillRect(0, 0, width, height);

  const sharedRegion = { x: 0, y: 0, width, height };
  const combineScale = (fineZoom: number) => state.scale * fineZoom;

  // Bild Y als volle Basis-Ebene (wie in der Live-Vorschau).
  drawPhotoIntoRegion(ctx, imgY, sharedRegion, {
    scale: combineScale(state.y.fineZoom),
    translateX: state.translateX + state.y.offsetX,
    translateY: state.translateY + state.y.offsetY,
    rotation: state.y.rotation,
    brightness: state.y.brightness,
  });

  // Bild X darüber, auf den linken Divider-Anteil begrenzt.
  const dividerX = (state.dividerPct / 100) * width;
  ctx.save();
  ctx.beginPath();
  ctx.rect(0, 0, dividerX, height);
  ctx.clip();
  drawPhotoIntoRegion(ctx, imgX, sharedRegion, {
    scale: combineScale(state.x.fineZoom),
    translateX: state.translateX + state.x.offsetX,
    translateY: state.translateY + state.x.offsetY,
    rotation: state.x.rotation,
    brightness: state.x.brightness,
  });
  ctx.restore();

  drawDivider(ctx, dividerX, height);
  if (showWatermark) drawWatermark(ctx, width, height);
}
```

- [ ] **Step 2: Verify the frontend type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors. This file has no test coverage (pure canvas drawing, no frontend test framework in this repo) — correctness is verified visually in Task 4's manual check.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/utils/compareExport.ts
git commit -m "feat: add canvas rendering utilities for comparison export"
```

---

### Task 2: Expose pane transform state via imperative refs

**Files:**
- Modify: `frontend/src/pages/Compare.tsx`

- [ ] **Step 1: Add imports for ref forwarding**

At the top of `frontend/src/pages/Compare.tsx`, extend the existing `import { useEffect, useRef, useState } from "react";` line to also import `forwardRef` and `useImperativeHandle`:

```tsx
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
```

- [ ] **Step 2: Convert `ZoomPane` to forward a ref exposing its export state**

Find the `ZoomPane` function declaration:

```tsx
function ZoomPane({
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
}: {
```

Replace the function signature and its closing to use `forwardRef`. Change:

```tsx
function ZoomPane({
```

to:

```tsx
export interface ZoomPaneHandle {
  getExportState: () => { scale: number; translateX: number; translateY: number; rotation: number };
}

const ZoomPane = forwardRef<ZoomPaneHandle, {
```

and change the closing `}) {` of the props type (right before the function body's opening `{`) — find:

```tsx
  onGridLineChange?: (index: number, value: number) => void;
}) {
  const { scale, translate, containerRef, isDragging, reset, setScaleFromSlider } = usePanZoom();
  const [rotation, setRotation] = useState(0);
```

replace with:

```tsx
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

  useImperativeHandle(ref, () => ({
    getExportState: () => ({ scale, translateX: translate.x, translateY: translate.y, rotation }),
  }));
```

Find the closing of the `ZoomPane` function (the final `}` right before the `/** Schieberegler-Vergleich ...` comment that starts `SliderComparePane`):

```tsx
        {showBrightnessSlider && brightness !== undefined && onBrightnessChange && (
          <BrightnessSlider value={brightness} onChange={onBrightnessChange} />
        )}
      </div>
    </div>
  );
}
```

Replace the trailing `}` (which closed the plain function) with `});` (which closes the `forwardRef` call):

```tsx
        {showBrightnessSlider && brightness !== undefined && onBrightnessChange && (
          <BrightnessSlider value={brightness} onChange={onBrightnessChange} />
        )}
      </div>
    </div>
  );
});
```

Check `translate` from `usePanZoom()` — confirm it has `.x`/`.y` fields (read `frontend/src/pages/Compare.tsx`'s `usePanZoom` hook definition or its usage in `transformStyle(translate, scale)` to confirm the shape before assuming `.x`/`.y`; adjust the `getExportState` mapping if the actual field names differ).

- [ ] **Step 3: Forward the ref through `ComparePane`**

Find:

```tsx
function ComparePane({
  label,
  src,
  filter,
  brightness,
  onBrightnessChange,
  showBrightnessSlider = true,
  showGrid,
  gridLines,
  onGridLineChange,
}: {
  label: string;
  src: string;
  filter: string | undefined;
  brightness: number;
  onBrightnessChange: (value: number) => void;
  showBrightnessSlider?: boolean;
  showGrid?: boolean;
  gridLines?: number[];
  onGridLineChange?: (index: number, value: number) => void;
}) {
  return (
    <figure className="overflow-hidden rounded-xl border border-white/5 bg-surface">
      <ZoomPane
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
}
```

Replace with (adds `forwardRef` pass-through):

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

- [ ] **Step 4: Add refs and wire them at the `ComparePane` call sites**

Inside the main `Compare()` component function, add (alongside the other `useRef`/`useState` declarations near the top):

```tsx
  const paneXRef = useRef<ZoomPaneHandle>(null);
  const paneYRef = useRef<ZoomPaneHandle>(null);
```

Find the side-by-side render block:

```tsx
      {!isAllPoses && result && mode === "side-by-side" && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <ComparePane
            label={formatDate(dateX)}
            src={resolveSrc(result.photo_x)}
```

Add `ref={paneXRef}` to the first `ComparePane` and `ref={paneYRef}` to the second one (find both `<ComparePane ... />` elements in that block and add the respective `ref` prop as the first prop on each).

- [ ] **Step 5: Add a matching `getExportState` to `SliderComparePane`**

In `SliderComparePane`, convert it to `forwardRef` the same way, exposing:

```tsx
export interface SliderPaneHandle {
  getExportState: () => {
    scale: number;
    translateX: number;
    translateY: number;
    dividerPct: number;
    x: { offsetX: number; offsetY: number; fineZoom: number; rotation: number };
    y: { offsetX: number; offsetY: number; fineZoom: number; rotation: number };
  };
}
```

Follow the exact same `forwardRef`/`useImperativeHandle` pattern as `ZoomPane` (Step 2 above) — wrap `SliderComparePane`'s function signature in `forwardRef<SliderPaneHandle, {...props...}>(function SliderComparePane({...}, ref) { ... })`, add `useImperativeHandle(ref, () => ({ getExportState: () => ({ scale, translateX: translate.x, translateY: translate.y, dividerPct, x: { offsetX: offsetX.x, offsetY: offsetX.y, fineZoom: fineZoomX, rotation: rotationX }, y: { offsetX: offsetY.x, offsetY: offsetY.y, fineZoom: fineZoomY, rotation: rotationY } }) }));` right after the existing `useState`/`useRef` declarations in that component, and change its closing `}` to `});`.

Add a ref in `Compare()`:

```tsx
  const sliderPaneRef = useRef<SliderPaneHandle>(null);
```

Find the `<SliderComparePane ... />` call site and add `ref={sliderPaneRef}` as its first prop.

- [ ] **Step 6: Verify the frontend type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors. This is the highest-risk task in the plan (converting two existing components to `forwardRef` without changing their rendered behavior) — if `tsc` reveals type mismatches in the `translate`/`offsetX`/`offsetY` field shapes assumed above, fix the `getExportState` mappings to match the actual hook/state shapes rather than changing the hooks themselves.

- [ ] **Step 7: Manual check in the browser**

Open Compare, side-by-side mode: zoom, pan, and rotate one photo — confirm the live preview still behaves exactly as before (the `forwardRef` conversion must be a no-op for rendered behavior). Repeat for slider mode.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/Compare.tsx
git commit -m "feat: expose pane zoom/pan/rotation state via imperative refs"
```

---

### Task 3: Export button + preview modal

**Files:**
- Create: `frontend/src/components/CompareExportModal.tsx`
- Modify: `frontend/src/pages/Compare.tsx`

- [ ] **Step 1: Create the preview modal component**

Write `frontend/src/components/CompareExportModal.tsx`:

```tsx
// frontend/src/components/CompareExportModal.tsx
import { useEffect, useRef, useState } from "react";
import type { ExportAspect } from "../utils/compareExport";
import { dimensionsFor } from "../utils/compareExport";

/** Vorschau-Dialog vor dem eigentlichen Download - siehe Design-Spec
 * "Compare-Export für Social Media". `render` zeichnet auf den
 * übergebenen Canvas für das gewählte Format; wird bei jedem
 * Format-Wechsel erneut aufgerufen. */
export function CompareExportModal({
  onClose,
  render,
  filename,
}: {
  onClose: () => void;
  render: (canvas: HTMLCanvasElement, aspect: ExportAspect) => void;
  filename: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [aspect, setAspect] = useState<ExportAspect>("1:1");

  useEffect(() => {
    if (canvasRef.current) render(canvasRef.current, aspect);
  }, [aspect, render]);

  const handleDownload = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.toBlob((blob) => {
      if (!blob) return;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    }, "image/png");
  };

  const dims = dimensionsFor(aspect);

  return (
    <div
      className="fixed inset-0 z-[90] flex items-center justify-center bg-black/70 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-lg rounded-xl border border-white/10 bg-surface p-6 shadow-2xl">
        <h2 className="mb-4 text-lg font-semibold text-white">Export Comparison</h2>

        <div className="mb-4 flex gap-2">
          <button
            type="button"
            onClick={() => setAspect("1:1")}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
              aspect === "1:1" ? "bg-accent text-slate-900" : "border border-white/15 text-white"
            }`}
          >
            1:1 (Instagram)
          </button>
          <button
            type="button"
            onClick={() => setAspect("4:3")}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
              aspect === "4:3" ? "bg-accent text-slate-900" : "border border-white/15 text-white"
            }`}
          >
            4:3
          </button>
        </div>

        <div className="mb-4 flex justify-center overflow-hidden rounded-lg bg-black/40">
          <canvas
            ref={canvasRef}
            style={{ maxWidth: "100%", aspectRatio: `${dims.width} / ${dims.height}` }}
          />
        </div>

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-white/15 px-4 py-2 text-sm font-medium text-white hover:bg-white/5"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleDownload}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90"
          >
            Download
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Wire the export button into `Compare.tsx`**

Add these imports at the top of `frontend/src/pages/Compare.tsx`:

```tsx
import { CompareExportModal } from "../components/CompareExportModal";
import {
  exportFilename,
  renderSideBySideToCanvas,
  renderSliderToCanvas,
  shouldShowWatermark,
} from "../utils/compareExport";
import { useCurrentUser } from "../hooks/useCurrentUser";
```

(Check whether `useCurrentUser` is already imported in this file before adding a duplicate line — if so, just reuse the existing import.)

Add state for the modal near the other `useState` declarations in `Compare()`:

```tsx
  const [showExportModal, setShowExportModal] = useState(false);
  const { data: currentUser } = useCurrentUser();
```

Add an "Export Comparison" button. Find where the AI-analysis button block is:

```tsx
      {((isAllPoses && allPosePairs.length > 0) || (!isAllPoses && result)) && (
        <div className="flex flex-col items-center gap-2">
          <button
            onClick={() => {
              show("Judge analyzing…");
              activeAiMutation.mutate();
            }}
```

Add a new button right after that closing `</div>` of the AI-analysis block, still conditioned on `!isAllPoses && result` (export only makes sense for a single concrete pose pair, not the "all poses" aggregate view):

```tsx
      {!isAllPoses && result && (
        <div className="flex justify-center">
          <button
            onClick={() => setShowExportModal(true)}
            className="rounded-lg border border-white/15 px-4 py-2 text-sm font-medium text-white hover:bg-white/5"
          >
            Export Comparison
          </button>
        </div>
      )}
```

Add the modal render at the end of the component's returned JSX, right before the final closing tag of the outermost wrapping element (read the file to find that exact spot):

```tsx
      {showExportModal && result && (
        <CompareExportModal
          onClose={() => setShowExportModal(false)}
          filename={exportFilename(clientName, dateX, dateY)}
          render={(canvas, aspect) => {
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
          }}
        />
      )}
```

Check the exact name of the client's display name variable in scope (used for `exportFilename`'s first argument) — this file already has the client loaded somewhere for the page header; find the correct variable (e.g. `clientQuery.data?.name` or similar) instead of assuming a bare `clientName` identifier exists, and adjust the call accordingly (e.g. `exportFilename(clientQuery.data?.name ?? "client", dateX, dateY)`).

- [ ] **Step 3: Verify the frontend type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Manual check in the browser**

Open Compare, select two dates/a pose, adjust zoom/rotation/brightness on both sides. Click "Export Comparison" — modal should open showing a rendered canvas matching the on-screen state. Switch between 1:1 and 4:3 — canvas re-renders. Click Download — a PNG file downloads with the expected filename. Repeat in slider mode. Log in as a non-paying account and confirm the watermark appears in the bottom-right corner of the exported image; log in as a coach with an active subscription and confirm it does NOT appear (can verify by temporarily setting `subscription_status` on a test user in the local DB).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/CompareExportModal.tsx frontend/src/pages/Compare.tsx
git commit -m "feat: add Export Comparison button and preview modal to Compare page"
```

---

### Task 4: Final review and finish

- [ ] **Step 1: Run the full frontend type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 2: Run the full backend test suite (sanity check — no backend files touched by this plan)**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: same pass count as before this branch (only the pre-existing unrelated flaky `test_gemini_key_is_scoped_per_account` may fail).

- [ ] **Step 3: Full manual regression pass on the Compare page**

Beyond the export feature itself, confirm the `forwardRef` conversion in Task 2 didn't regress any existing Compare functionality: zoom via mouse wheel, pan via click-drag, double-click reset, rotation slider, brightness slider, grid overlay toggle, AI analysis button, pose navigation — all exactly as before.

- [ ] **Step 4: Use superpowers:finishing-a-development-branch**

Follow that skill to present merge/PR/keep/discard options and complete the branch.
