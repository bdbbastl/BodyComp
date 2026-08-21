import { SliderControl } from "./SliderControl";

export const ROTATION_MIN = -15;
export const ROTATION_MAX = 15;
const STEP = 0.5;

/** Feinjustierung der Bildneigung (Kamera-Tilt-Korrektur) - kleiner
 * Wertebereich reicht aus, echte Handyfotos sind selten stärker als ein
 * paar Grad schräg. */
export function RotationSlider({
  degrees,
  onChange,
  label = "Tilt",
}: {
  degrees: number;
  onChange: (value: number) => void;
  label?: string;
}) {
  return (
    <SliderControl
      label={label}
      value={degrees}
      min={ROTATION_MIN}
      max={ROTATION_MAX}
      step={STEP}
      decimals={1}
      onChange={onChange}
      suffix="°"
    />
  );
}
