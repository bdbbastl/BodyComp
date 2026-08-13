import { SliderControl } from "./SliderControl";

export interface Offset {
  x: number;
  y: number;
}

const OFFSET_LIMIT = 150; // px
const STEP = 1;

/** Feinjustierung der Bild-POSITION (horizontal + vertikal, in px) -
 * unabhängig vom gemeinsamen Klick+Ziehen-Pan (das immer beide Bilder
 * gleich verschiebt). Für "linkes Bild sitzt etwas höher als rechtes"
 * u.ä. braucht es einen Versatz pro Bild statt eines gemeinsamen. */
export function PositionSlider({
  offset,
  onChange,
}: {
  offset: Offset;
  onChange: (offset: Offset) => void;
}) {
  return (
    <div className="space-y-3">
      <SliderControl
        icon="↔"
        label="Position horizontal"
        value={offset.x}
        min={-OFFSET_LIMIT}
        max={OFFSET_LIMIT}
        step={STEP}
        onChange={(x) => onChange({ ...offset, x })}
        suffix="px"
      />
      <SliderControl
        icon="↕"
        label="Position vertikal"
        value={offset.y}
        min={-OFFSET_LIMIT}
        max={OFFSET_LIMIT}
        step={STEP}
        onChange={(y) => onChange({ ...offset, y })}
        suffix="px"
      />
    </div>
  );
}
