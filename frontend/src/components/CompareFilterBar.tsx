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
