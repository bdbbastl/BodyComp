// frontend/src/components/BusyOverlay.tsx
import { useBusyOverlayState } from "../contexts/BusyOverlayContext";

/** Rendert nichts, solange kein Vorgang aktiv ist. Vollbild, blockiert
 * komplett (kein pointer-events durch, kein Escape) - siehe Design-Spec
 * "Usability-Fixes Runde 2" Abschnitt 3+4. */
export function BusyOverlay() {
  const { active, label, progressPercent } = useBusyOverlayState();
  if (!active) return null;

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/70">
      <div className="w-full max-w-xs space-y-3 rounded-xl border border-white/10 bg-surface p-6 text-center shadow-2xl">
        <p className="text-sm font-medium text-white">{label}</p>
        {progressPercent !== null ? (
          <div className="space-y-1">
            <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
              <div
                className="h-full rounded-full bg-accent transition-all duration-150"
                style={{ width: `${Math.max(0, Math.min(100, progressPercent))}%` }}
              />
            </div>
            <p className="text-xs text-slate-400">{Math.round(progressPercent)}%</p>
          </div>
        ) : (
          <div className="mx-auto h-6 w-6 animate-spin rounded-full border-2 border-white/20 border-t-accent" />
        )}
      </div>
    </div>
  );
}
