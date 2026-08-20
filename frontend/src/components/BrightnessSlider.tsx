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
