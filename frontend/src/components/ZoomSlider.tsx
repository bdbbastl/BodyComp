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
