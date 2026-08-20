# Compare-Steuerungsbereich Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Compare page's three stacked control blocks and its slider stacks with a compact icon-button header, a single filter row, and per-photo adjustment icons that open one slider at a time — so the photos move up the page.

**Architecture:** Four presentational components are extracted from `Compare.tsx` (currently ~1130 lines): `IconButton`, `BrightnessSlider` (moved out to sit beside the existing `ZoomSlider`/`RotationSlider`/`PositionSlider`), `PaneAdjustments` (icon row + single-slider popover), and `CompareFilterBar`. `Compare.tsx` keeps all selection and view state and passes it down. No zoom/pan, export, or AI logic changes.

**Tech Stack:** React 18 + TypeScript + Tailwind + `lucide-react` (already a dependency, used so far only in `ClientShell.tsx`). Verification via `npx tsc --noEmit`, `npm test` (node --test, pure logic only), and a manual browser pass — this repo has no component test framework and adding one is out of scope.

**Spec:** `docs/superpowers/specs/2026-08-20-compare-controls-redesign-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `frontend/src/components/IconButton.tsx` | **Create.** One icon button; owns the visual states (ghost/accent/active/pending/disabled/dot/badge) and the accessibility contract. |
| `frontend/src/components/BrightnessSlider.tsx` | **Create.** Moved out of `Compare.tsx` so it sits beside the other sliders, and so the brightness constants have one home. |
| `frontend/src/components/PaneAdjustments.tsx` | **Create.** Icon row under one photo + popover holding exactly one slider. Owns only "which tool is open". |
| `frontend/src/components/CompareFilterBar.tsx` | **Create.** Pose select with ‹ › arrows, Date X → Date Y, mode switch. |
| `frontend/src/pages/Compare.tsx` | **Modify.** Wire everything in; delete `PoseNavBar` and the local `BrightnessSlider`; move the two checkboxes into the header. |

`SliderControl`, `ZoomSlider`, `RotationSlider` and `PositionSlider` keep their current behaviour — `PaneAdjustments` renders them inside its popover.

### Two facts to know before starting

**The two panes have different controls.** `ZoomPane` (side-by-side) has zoom, rotation and exposure. `SliderComparePane` has, per image, a *fine* zoom, rotation and a position offset — plus one shared zoom for the whole container. `PaneAdjustments` therefore takes each tool as optional and renders only what it is given.

**Brightness currently lives in two places.** In side-by-side it is passed into `ZoomPane`; in slider mode `Compare.tsx` renders a separate card of two `BrightnessSlider`s *below* the pane (`Compare.tsx:552`). Task 9 folds that card into the per-image icon rows and deletes it.

---

### Task 1: `IconButton` component

**Files:**
- Create: `frontend/src/components/IconButton.tsx`

- [ ] **Step 1: Write the component**

Create `frontend/src/components/IconButton.tsx`:

```tsx
import type { LucideIcon } from "lucide-react";
import { Loader2 } from "lucide-react";

/**
 * Icon-Button ohne sichtbares Textlabel - genutzt im Compare-Header
 * (Ansichtsschalter + Aktionen) und in der Reglerleiste unter jedem Foto.
 *
 * `label` ist bewusst ein Pflicht-Prop und NICHT optional: Der Button
 * zeigt keinen Text, also ist das Label die einzige Beschriftung für
 * Screenreader und der einzige Tooltip für sehende Nutzer.
 */
export function IconButton({
  icon: Icon,
  label,
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
  const box = size === "sm" ? "h-8 w-8" : "h-9 w-9";
  const glyph = size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4";

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

- [ ] **Step 2: Verify it type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors. If the installed `lucide-react` does not export the `LucideIcon` type, replace that import with `import type { ComponentType } from "react";` and type `icon` as `ComponentType<{ className?: string }>`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/IconButton.tsx
git commit -m "feat: add IconButton component for compare controls"
```

---

### Task 2: Move `BrightnessSlider` into its own file

`Compare.tsx` defines `BrightnessSlider` locally along with `BRIGHTNESS_MIN`/`MAX`/`DEFAULT`. `PaneAdjustments` will need both. Moving it out mirrors how `ZoomSlider`, `RotationSlider` and `PositionSlider` already live in `components/`, and keeps the constants in exactly one place.

**Files:**
- Create: `frontend/src/components/BrightnessSlider.tsx`
- Modify: `frontend/src/pages/Compare.tsx`

- [ ] **Step 1: Create the component file**

Create `frontend/src/components/BrightnessSlider.tsx`:

```tsx
import { SliderControl } from "./SliderControl";

export const BRIGHTNESS_MIN = 50;
export const BRIGHTNESS_MAX = 250;
export const BRIGHTNESS_DEFAULT = 100;

/** Belichtungs-Regler unter einem Bild - jedes Bild wird individuell
 * gesteuert (100% = unverändertes Original). */
export function BrightnessSlider({
  value,
  onChange,
}: {
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <SliderControl
      label="Exposure"
      value={value}
      min={BRIGHTNESS_MIN}
      max={BRIGHTNESS_MAX}
      step={1}
      onChange={onChange}
      suffix="%"
    />
  );
}
```

The `icon="☀"` from the original is dropped: inside the new popover the tool is already named by its label and by the icon on the button that opened it.

- [ ] **Step 2: Delete the local copy in `Compare.tsx`**

In `frontend/src/pages/Compare.tsx`, delete these three constants near the top of the file:

```tsx
const BRIGHTNESS_MIN = 50;
const BRIGHTNESS_MAX = 250;
const BRIGHTNESS_DEFAULT = 100;
```

and delete the whole local component:

```tsx
/** Belichtungs-Slider unter einem Bild - jedes Bild wird individuell
 * gesteuert (100% = unverändertes Original). */
function BrightnessSlider({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  return (
    <SliderControl
      icon="☀"
      label="Exposure"
      value={value}
      min={BRIGHTNESS_MIN}
      max={BRIGHTNESS_MAX}
      step={1}
      onChange={onChange}
      suffix="%"
    />
  );
}
```

- [ ] **Step 3: Import them instead**

Add to the imports at the top of `Compare.tsx`:

```tsx
import { BrightnessSlider, BRIGHTNESS_DEFAULT } from "../components/BrightnessSlider";
```

`BRIGHTNESS_DEFAULT` is still used by the `brightnessX`/`brightnessY` `useState` initialisers and by `filterFor`. `BRIGHTNESS_MIN`/`MAX` are no longer referenced in `Compare.tsx`.

- [ ] **Step 4: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors. If `SliderControl` is now unused in `Compare.tsx`, remove its import.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/BrightnessSlider.tsx frontend/src/pages/Compare.tsx
git commit -m "refactor: move BrightnessSlider and its constants into their own module"
```

---

### Task 3: `PaneAdjustments` component

**Files:**
- Create: `frontend/src/components/PaneAdjustments.tsx`

- [ ] **Step 1: Write the component**

Create `frontend/src/components/PaneAdjustments.tsx`:

```tsx
import { useEffect, useRef, useState } from "react";
import { Move, RotateCcw, RotateCw, Sun, ZoomIn } from "lucide-react";
import { IconButton } from "./IconButton";
import { ZoomSlider } from "./ZoomSlider";
import { RotationSlider } from "./RotationSlider";
import { PositionSlider } from "./PositionSlider";
import type { Offset } from "./PositionSlider";
import { BrightnessSlider, BRIGHTNESS_DEFAULT } from "./BrightnessSlider";
import { ZOOM_MIN } from "../hooks/usePanZoom";

type Tool = "zoom" | "rotation" | "position" | "exposure";

const ROTATION_DEFAULT = 0;

/**
 * Reglerleiste unter einem Vergleichsfoto: eine Reihe Icons, von denen
 * jeweils EINES ein Popover mit genau seinem Regler öffnet.
 *
 * Die Komponente hält bewusst keinen Reglerwert - nur die Information,
 * welches Werkzeug gerade offen ist. Alle Werte bleiben dort, wo sie
 * heute liegen (Zoom/Neigung/Position in ZoomPane bzw.
 * SliderComparePane, Exposure in Compare.tsx), damit die ref-basierte
 * Anbindung des Export-Renderings unberührt bleibt.
 *
 * Position und Exposure sind optional, weil die beiden Pane-Typen
 * unterschiedliche Regler haben: Side-by-Side kennt keinen Versatz pro
 * Bild, der Schieberegler-Vergleich keinen eigenen Exposure-Regler pro
 * Pane-Komponente.
 */
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
  const [openTool, setOpenTool] = useState<Tool | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  // Escape und Klick außerhalb schließen das Popover. Beides bewusst auf
  // Dokumentebene, damit auch ein Klick ins Foto sauber schließt - der
  // Foto-Container hat eigene native Maus-Handler (siehe usePanZoom).
  useEffect(() => {
    if (!openTool) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpenTool(null);
    }
    function onDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpenTool(null);
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [openTool]);

  const hasPosition = offset !== undefined && onOffsetChange !== undefined;
  const hasExposure = brightness !== undefined && onBrightnessChange !== undefined;

  const zoomTouched = scale !== ZOOM_MIN;
  const rotationTouched = rotation !== ROTATION_DEFAULT;
  const positionTouched = hasPosition && (offset!.x !== 0 || offset!.y !== 0);
  const exposureTouched = hasExposure && brightness !== BRIGHTNESS_DEFAULT;
  const anyTouched = zoomTouched || rotationTouched || positionTouched || exposureTouched;

  function toggle(tool: Tool) {
    setOpenTool((current) => (current === tool ? null : tool));
  }

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

      {openTool && (
        <div className="mt-2 rounded-lg border border-accent/30 bg-background p-3 shadow-xl">
          {openTool === "zoom" && <ZoomSlider scale={scale} onChange={onScaleChange} />}
          {openTool === "rotation" && (
            <RotationSlider degrees={rotation} onChange={onRotationChange} />
          )}
          {openTool === "position" && hasPosition && (
            <PositionSlider offset={offset!} onChange={onOffsetChange!} />
          )}
          {openTool === "exposure" && hasExposure && (
            <BrightnessSlider value={brightness!} onChange={onBrightnessChange!} />
          )}
        </div>
      )}
    </div>
  );
}
```

`onReset` is passed in whole rather than assembled here, because the two pane types reset different things — see Tasks 8 and 9.

- [ ] **Step 2: Verify it type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors. `PositionSlider.tsx` already exports the `Offset` interface.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/PaneAdjustments.tsx
git commit -m "feat: add PaneAdjustments icon row with single-slider popover"
```

---

### Task 4: Drop the remaining emoji icons from the sliders

Inside the popover each slider is already identified by its label and by the icon on the button that opened it, so the emoji are now duplicates.

**Files:**
- Modify: `frontend/src/components/ZoomSlider.tsx`
- Modify: `frontend/src/components/RotationSlider.tsx`
- Modify: `frontend/src/components/PositionSlider.tsx`

- [ ] **Step 1: `ZoomSlider`**

Find:

```tsx
    <SliderControl
      icon="🔍"
      label={label}
```

Replace with:

```tsx
    <SliderControl
      label={label}
```

- [ ] **Step 2: `RotationSlider`**

Find:

```tsx
    <SliderControl
      icon="↻"
      label={label}
```

Replace with:

```tsx
    <SliderControl
      label={label}
```

- [ ] **Step 3: `PositionSlider`**

It renders two `SliderControl`s. Remove `icon="↔"` from the horizontal one and `icon="↕"` from the vertical one, leaving their `label` props untouched.

- [ ] **Step 4: Check the other consumer**

Run: `cd frontend && grep -rn "ZoomSlider" src/`

`ZoomSlider` is also used by the Timeline lightbox. The `icon` prop on `SliderControl` is optional, so this is safe — but look at the lightbox in the browser during Task 10 and, if it reads bare without the magnifier, pass `icon` at that call site rather than restoring it here.

- [ ] **Step 5: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ZoomSlider.tsx frontend/src/components/RotationSlider.tsx frontend/src/components/PositionSlider.tsx
git commit -m "refactor: drop emoji icons from compare adjustment sliders"
```

---

### Task 5: `CompareFilterBar` component

**Files:**
- Create: `frontend/src/components/CompareFilterBar.tsx`

- [ ] **Step 1: Write the component**

Create `frontend/src/components/CompareFilterBar.tsx`:

```tsx
import { ChevronLeft, ChevronRight, Columns2, MoveHorizontal } from "lucide-react";
import type { Pose } from "../types";
import { numberedPoseOptionLabel } from "../utils/poseLabel";

export type CompareMode = "side-by-side" | "slider";

const SELECT_CLASS =
  "rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white focus:border-accent focus:outline-none disabled:opacity-40";

const GROUP_LABEL_CLASS =
  "mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500";

const ARROW_CLASS =
  "flex h-9 w-8 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-30";

/**
 * Eine Zeile für die gesamte Auswahl: Pose (mit Vor/Zurück-Pfeilen),
 * verglichener Zeitraum als "Datum X -> Datum Y" und der Modus-Umschalter.
 *
 * Die Pfeile ersetzen die frühere eigenständige PoseNavBar - beide
 * steuerten denselben Wert und kosteten zusammen eine ganze Bildschirm-
 * zeile. `onNavigate` läuft zyklisch durch die Posenliste (siehe
 * goToPose in Compare.tsx), deshalb sind die Pfeile an den Rändern der
 * Liste NICHT deaktiviert - nur im Modus "All poses".
 */
export function CompareFilterBar({
  poses,
  poseValue,
  onPoseChange,
  onNavigate,
  navigationDisabled,
  allPosesValue,
  dateX,
  dateY,
  onDateXChange,
  onDateYChange,
  availableDates,
  datesDisabled,
  datePlaceholder,
  formatDate,
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
  return (
    <div className="flex flex-wrap items-end gap-5 rounded-xl border border-white/5 bg-surface p-4">
      <div>
        <div className={GROUP_LABEL_CLASS}>Pose</div>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => onNavigate(-1)}
            disabled={navigationDisabled}
            aria-label="Previous pose"
            className={ARROW_CLASS}
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <select
            value={poseValue}
            onChange={(e) => onPoseChange(e.target.value)}
            aria-label="Pose"
            className={SELECT_CLASS}
          >
            <option value="">Choose pose…</option>
            <option value={allPosesValue}>All poses</option>
            {poses.map((p, index) => (
              <option key={p.id} value={p.id}>
                {numberedPoseOptionLabel(index, p.name)}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => onNavigate(1)}
            disabled={navigationDisabled}
            aria-label="Next pose"
            className={ARROW_CLASS}
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div>
        <div className={GROUP_LABEL_CLASS}>Vergleich</div>
        <div className="flex items-center gap-2">
          <select
            value={dateX}
            onChange={(e) => onDateXChange(e.target.value)}
            disabled={datesDisabled}
            aria-label="Date X"
            className={SELECT_CLASS}
          >
            <option value="">{datePlaceholder}</option>
            {availableDates.map((d) => (
              <option key={d} value={d}>
                {formatDate(d)}
              </option>
            ))}
          </select>
          <span className="text-slate-500" aria-hidden="true">
            →
          </span>
          <select
            value={dateY}
            onChange={(e) => onDateYChange(e.target.value)}
            disabled={datesDisabled}
            aria-label="Date Y"
            className={SELECT_CLASS}
          >
            <option value="">{datePlaceholder}</option>
            {availableDates.map((d) => (
              <option key={d} value={d}>
                {formatDate(d)}
              </option>
            ))}
          </select>
        </div>
      </div>

      {showModeSwitch && (
        <div className="ml-auto flex gap-1 rounded-full bg-black/30 p-1">
          <button
            type="button"
            onClick={() => onModeChange("side-by-side")}
            className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
              mode === "side-by-side"
                ? "bg-accent text-slate-900"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <Columns2 className="h-3.5 w-3.5" />
            Side-by-Side
          </button>
          <button
            type="button"
            onClick={() => onModeChange("slider")}
            className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
              mode === "slider" ? "bg-accent text-slate-900" : "text-slate-400 hover:text-white"
            }`}
          >
            <MoveHorizontal className="h-3.5 w-3.5" />
            Slider
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify it type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/CompareFilterBar.tsx
git commit -m "feat: add CompareFilterBar with inline pose navigation"
```

---

### Task 6: Move the actions into the page header

**Files:**
- Modify: `frontend/src/pages/Compare.tsx`

- [ ] **Step 1: Add the imports**

After the existing `import PageHeader from "../components/PageHeader";` line, add:

```tsx
import { Grid3x3, ImageDown, Scan, Sparkles } from "lucide-react";
import { IconButton } from "../components/IconButton";
```

- [ ] **Step 2: Add the `canAnalyze` helper**

The old AI button was conditionally *rendered*. As a header button it stays mounted and is *disabled* instead, so the icon row does not jump around as the selection changes. Next to the existing `missingNormalized` declaration inside `Compare()`, add:

```tsx
  // Früher steuerte diese Bedingung, OB der KI-Button überhaupt gerendert
  // wird. Im Header bleibt der Button dauerhaft sichtbar und wird
  // stattdessen deaktiviert - sonst würde die Icon-Reihe je nach Auswahl
  // ihre Breite ändern.
  const canAnalyze = (isAllPoses && allPosePairs.length > 0) || (!isAllPoses && !!result);
```

- [ ] **Step 3: Replace the page header**

Find:

```tsx
      <PageHeader title="Compare" />
```

Replace with:

```tsx
      <PageHeader
        title="Compare"
        actions={
          <>
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
          </>
        }
      />
```

- [ ] **Step 4: Replace the old AI block with just its status line**

Find and delete this whole block:

```tsx
      {((isAllPoses && allPosePairs.length > 0) || (!isAllPoses && result)) && (
        <div className="flex flex-col items-center gap-2">
          <button
            onClick={() => {
              show("Judge analyzing…");
              activeAiMutation.mutate();
            }}
            disabled={activeAiMutation.isPending}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {activeAiMutation.isPending
              ? "Judge analyzing…"
              : isAllPoses
                ? `🥊 AI overall analysis (${allPosePairs.length} poses)`
                : "🥊 AI analysis (judge rating)"}
          </button>
          {activeAiMutation.isPending && (
            <p className="flex items-center gap-2 text-xs text-slate-400">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-accent" />
              AI is still working… {elapsedSeconds}s
              {elapsedSeconds > 20 && " (Gemini retries automatically under server load)"}
            </p>
          )}
        </div>
      )}
```

Put this in its place:

```tsx
      {activeAiMutation.isPending && (
        <p className="flex items-center justify-center gap-2 text-xs text-accent">
          <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-accent" />
          Judge analysiert… {elapsedSeconds}s
          {elapsedSeconds > 20 && " (Gemini wiederholt automatisch bei Serverlast)"}
        </p>
      )}
```

- [ ] **Step 5: Delete the old export button**

Find and delete:

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

- [ ] **Step 6: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Compare.tsx
git commit -m "feat: move compare actions into icon-button page header"
```

---

### Task 7: Swap in `CompareFilterBar` and delete `PoseNavBar`

**Files:**
- Modify: `frontend/src/pages/Compare.tsx`

- [ ] **Step 1: Add the import**

```tsx
import { CompareFilterBar } from "../components/CompareFilterBar";
```

- [ ] **Step 2: Replace the filter card**

Find the block that starts with:

```tsx
      <div className="flex flex-wrap items-end gap-4 rounded-xl border border-white/5 bg-surface p-4">
        <label className="flex flex-col gap-1 text-sm text-slate-400">
          Pose
```

and ends after the `Alignment grid` checkbox label with its closing `</div>`. Replace the entire block with:

```tsx
      <CompareFilterBar
        poses={poses}
        poseValue={poseSelection === "" ? "" : String(poseSelection)}
        onPoseChange={(value) =>
          setPoseSelection(value === "" ? "" : value === ALL_POSES ? ALL_POSES : Number(value))
        }
        onNavigate={goToPose}
        navigationDisabled={isAllPoses || poses.length === 0}
        allPosesValue={ALL_POSES}
        dateX={dateX}
        dateY={dateY}
        onDateXChange={setDateX}
        onDateYChange={setDateY}
        availableDates={availableDates}
        datesDisabled={poseSelection === "" || availableDates.length === 0}
        datePlaceholder={poseSelection === "" ? "Choose pose first…" : "Choose date…"}
        formatDate={formatDate}
        mode={mode}
        onModeChange={setMode}
        showModeSwitch={!isAllPoses}
      />
```

Both checkboxes are deliberately gone — they became header toggles in Task 6.

- [ ] **Step 3: Delete the `PoseNavBar` render**

Find and delete:

```tsx
      {poses.length > 0 && dateX !== "" && dateY !== "" && (
        <PoseNavBar poses={poses} currentPoseId={poseSelection} onNavigate={goToPose} disabled={isAllPoses} />
      )}
```

- [ ] **Step 4: Delete the `PoseNavBar` component**

Delete the whole `function PoseNavBar({ poses, currentPoseId, onNavigate, disabled }: { … }) { … }` declaration, ending just before the `/** Belichtungs-Slider unter einem Bild …` comment position (that component was already removed in Task 2).

- [ ] **Step 5: Verify nothing dangles**

Run: `cd frontend && grep -n "PoseNavBar" src/pages/Compare.tsx`
Expected: no output.

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors. Remove any import that is now unused in `Compare.tsx` — likely `numberedPoseOptionLabel`, and possibly the `Pose` type if nothing else references it.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Compare.tsx
git commit -m "feat: replace compare filter card and pose nav with single filter bar"
```

---

### Task 8: `PaneAdjustments` in the side-by-side pane

**Files:**
- Modify: `frontend/src/pages/Compare.tsx`

- [ ] **Step 1: Add the import**

```tsx
import { PaneAdjustments } from "../components/PaneAdjustments";
```

- [ ] **Step 2: Replace the control block inside `ZoomPane`**

Find, at the end of `ZoomPane`'s JSX:

```tsx
      <div className="space-y-4 p-3.5">
        {caption && <p className="text-sm font-medium text-slate-300">{caption}</p>}
        <ZoomSlider scale={scale} onChange={setScaleFromSlider} />
        <RotationSlider degrees={rotation} onChange={setRotation} />
        {showBrightnessSlider && brightness !== undefined && onBrightnessChange && (
          <BrightnessSlider value={brightness} onChange={onBrightnessChange} />
        )}
      </div>
```

Replace with:

```tsx
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

`reset` already comes from `usePanZoom()` in this component — it is the same function the container's double-click uses, so double-click behaviour is unchanged. The reset button additionally clears rotation and exposure, which double-click does not.

- [ ] **Step 3: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors. `ZoomSlider` and `RotationSlider` may now be unused in `Compare.tsx` — leave their imports until Task 9 is done, since `SliderComparePane` still uses `ZoomSlider` for the shared zoom.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Compare.tsx
git commit -m "feat: use PaneAdjustments icon row in side-by-side compare pane"
```

---

### Task 9: `PaneAdjustments` in the slider pane

This pane has, per image, a fine zoom, a rotation and a position offset. Its exposure sliders currently sit in a **separate card below the pane**, rendered by `Compare.tsx`. This task folds them into the per-image icon rows and deletes that card, so both modes behave the same.

**Files:**
- Modify: `frontend/src/pages/Compare.tsx`

- [ ] **Step 1: Add brightness props to `SliderComparePane`**

`SliderComparePane` receives `filterX`/`filterY` (CSS filter strings) but not the underlying values. Add four props to its props type, next to `filterY`:

```tsx
  brightnessX: number;
  onBrightnessXChange: (value: number) => void;
  brightnessY: number;
  onBrightnessYChange: (value: number) => void;
```

and add them to the destructured parameter list of the `forwardRef` render function, next to `filterY`:

```tsx
  { srcX, srcY, filterX, filterY, brightnessX, onBrightnessXChange, brightnessY, onBrightnessYChange, altX, altY, showGrid, gridLines, onGridLineChange },
```

Use the exact existing parameter order from the file — insert the four new names, do not reorder the others.

- [ ] **Step 2: Replace the per-image slider groups**

Find:

```tsx
      <div className="mx-auto max-w-2xl space-y-5 rounded-xl border border-white/5 bg-surface p-4">
        <ZoomSlider label="Zoom (shared)" scale={scale} onChange={setScaleFromSlider} />
        <div className="grid grid-cols-1 gap-x-8 gap-y-5 border-t border-white/5 pt-5 sm:grid-cols-2">
          <div className="space-y-4">
            <p className="text-sm font-medium text-slate-300">{altX}</p>
            <ZoomSlider label="Zoom" scale={fineZoomX} onChange={setFineZoomX} />
            <RotationSlider degrees={rotationX} onChange={setRotationX} />
            <PositionSlider offset={offsetX} onChange={setOffsetX} />
          </div>
          <div className="space-y-4">
            <p className="text-sm font-medium text-slate-300">{altY}</p>
            <ZoomSlider label="Zoom" scale={fineZoomY} onChange={setFineZoomY} />
            <RotationSlider degrees={rotationY} onChange={setRotationY} />
            <PositionSlider offset={offsetY} onChange={setOffsetY} />
          </div>
        </div>
      </div>
```

Replace with:

```tsx
      <div className="mx-auto max-w-2xl space-y-4 rounded-xl border border-white/5 bg-surface p-4">
        <ZoomSlider label="Zoom (shared)" scale={scale} onChange={setScaleFromSlider} />
        <div className="grid grid-cols-1 gap-x-8 border-t border-white/5 pt-3 sm:grid-cols-2">
          <div>
            <p className="px-3 text-sm font-medium text-slate-300">{altX}</p>
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
          </div>
          <div>
            <p className="px-3 text-sm font-medium text-slate-300">{altY}</p>
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
          </div>
        </div>
      </div>
```

The per-image reset deliberately does **not** touch the shared `scale`/`translate` — those belong to the whole container and are reset by double-clicking it, exactly as today.

Add the import for the default at the top of `Compare.tsx` if Task 2 did not already leave it there:

```tsx
import { BrightnessSlider, BRIGHTNESS_DEFAULT } from "../components/BrightnessSlider";
```

- [ ] **Step 3: Pass the new props at the call site**

Find the `<SliderComparePane … />` call (around `Compare.tsx:539`) and add, after `filterY`:

```tsx
            brightnessX={brightnessX}
            onBrightnessXChange={setBrightnessX}
            brightnessY={brightnessY}
            onBrightnessYChange={setBrightnessY}
```

- [ ] **Step 4: Delete the separate brightness card**

Directly below that call sits a card rendering two `BrightnessSlider`s:

```tsx
          <div className="mx-auto grid max-w-2xl grid-cols-1 gap-x-8 gap-y-4 rounded-xl border border-white/5 bg-surface p-4 sm:grid-cols-2">
            <BrightnessSlider
              value={brightnessX}
              onChange={setBrightnessX}
            />
            <BrightnessSlider
              value={brightnessY}
              onChange={setBrightnessY}
            />
          </div>
```

Delete the whole card — the sliders now live in the per-image icon rows.

- [ ] **Step 5: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

Run: `cd frontend && grep -n "RotationSlider\|PositionSlider\|BrightnessSlider" src/pages/Compare.tsx`

If any of these are no longer referenced in `Compare.tsx`, delete their imports. `ZoomSlider` must stay — the shared zoom still uses it.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Compare.tsx
git commit -m "feat: use PaneAdjustments icon rows in slider compare pane"
```

---

### Task 10: Full verification and finish

- [ ] **Step 1: Type-check and build**

Run: `cd frontend && npx tsc --noEmit && npx vite build`
Expected: no type errors, build succeeds.

- [ ] **Step 2: Run the existing tests**

Run: `cd frontend && npm test`
Expected: `pass 8`, `fail 0`. These cover the export geometry and must be unaffected by this work.

- [ ] **Step 3: Manual browser pass — side-by-side**

Start the dev server through the preview tooling (never `npm run dev` via a shell tool) and check:

- Mouse-wheel zoom over a photo, click-drag to pan while zoomed, double-click to reset — unchanged
- Open each adjustment popover; the slider moves the photo
- The accent dot appears on an icon once its value leaves the default and disappears on reset
- Escape closes a popover; a click outside closes it; clicking a second icon switches tools
- The reset icon clears zoom, pan, rotation and exposure, then becomes disabled
- The two header toggles behave like the old checkboxes; inspect the DOM and confirm `aria-pressed` flips
- Tab through the header and an icon row: every button shows a visible focus ring
- Start the AI analysis: the header icon shows a spinner and the seconds counter appears below
- Open the export modal from the header icon and download an image

- [ ] **Step 4: Manual browser pass — slider mode**

- The shared zoom slider still moves both images together
- Per image: fine zoom, rotation, position and exposure all work from the icon row
- The old separate exposure card is gone
- Per-image reset clears that image's four values but leaves the shared zoom/pan alone
- Double-clicking the container still resets the shared zoom/pan

- [ ] **Step 5: Manual browser pass — All poses**

- The export icon is absent
- The AI icon shows the pose count as a badge
- The pose arrows are disabled

- [ ] **Step 6: Check the arrow keys and the lightbox**

With focus outside any form field, press ← and → — the pose changes and wraps around at both ends of the list.

Open a photo in the Timeline lightbox and confirm its zoom slider still reads well after Task 4 removed the magnifier emoji.

- [ ] **Step 7: Use superpowers:finishing-a-development-branch**

Follow that skill to complete the branch.
