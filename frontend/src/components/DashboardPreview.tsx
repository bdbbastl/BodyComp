// frontend/src/components/DashboardPreview.tsx

/** Stilisierte, rein CSS-basierte Vorschau des Coach-Dashboards für den
 * Landing-Page-Hero - siehe Design-Spec "Dashboard & Landing-Page Visual
 * Refresh" Abschnitt "Hero-Bereich". Platzhalter bis ein echter
 * Screenshot des fertigen Dashboards existiert (braucht das fertige
 * Redesign aus Task 4 als Motiv). */
export function DashboardPreview() {
  return (
    <div aria-hidden="true" className="mx-auto max-w-sm rounded-xl border border-white/10 bg-surface p-3 shadow-2xl shadow-black/40">
      <div className="mb-3 flex gap-1.5">
        <div className="h-2 w-2 rounded-full bg-slate-600" />
        <div className="h-2 w-2 rounded-full bg-slate-600" />
        <div className="h-2 w-2 rounded-full bg-slate-600" />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-lg bg-black/30 p-2">
          <div className="mb-1 h-1.5 w-8 rounded bg-slate-600" />
          <div className="text-lg font-semibold text-accent">4</div>
          <div className="mt-1 flex h-4 items-end gap-[2px]">
            {/* Placeholder demo bar heights for mockup preview */}
            {[40, 70, 55, 90].map((h, i) => (
              <div key={i} className="w-1 rounded-sm bg-accent/50" style={{ height: `${h}%` }} />
            ))}
          </div>
        </div>
        <div className="rounded-lg bg-black/30 p-2">
          <div className="mb-1 h-1.5 w-10 rounded bg-slate-600" />
          <div className="text-lg font-semibold text-accent">2</div>
        </div>
      </div>
      <div className="mt-2 rounded-lg bg-black/30 p-2">
        <div className="mb-1.5 h-1.5 w-14 rounded bg-slate-600" />
        <div className="flex items-center gap-1.5 py-1">
          <div className="h-4 w-4 rounded-full bg-cyan-500/30" />
          <div className="h-1.5 flex-1 rounded bg-slate-700" />
        </div>
        <div className="flex items-center gap-1.5 py-1">
          <div className="h-4 w-4 rounded-full bg-violet-500/30" />
          <div className="h-1.5 flex-1 rounded bg-slate-700" />
        </div>
      </div>
    </div>
  );
}
