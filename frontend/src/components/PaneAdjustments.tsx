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
