import { ZOOM_MAX, ZOOM_MIN } from "../hooks/usePanZoom";
import { SliderControl } from "./SliderControl";

const STEP = 0.05;

/** Feinstufiger Zoom-Regler (zusätzlich zum Mausrad) - v.a. beim
 * Schieberegler-Vergleich und in der Timeline-Lightbox nützlich, um den
 * Ausschnitt exakt passend einzustellen. */
export function ZoomSlider({
  scale,
  onChange,
  label = "Zoom",
}: {
  scale: number;
  onChange: (value: number) => void;
  label?: string;
}) {
  return (
    <SliderControl
      label={label}
      value={scale}
      min={ZOOM_MIN}
      max={ZOOM_MAX}
      step={STEP}
      decimals={2}
      onChange={onChange}
      suffix="×"
    />
  );
}
