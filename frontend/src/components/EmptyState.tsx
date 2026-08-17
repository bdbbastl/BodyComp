// frontend/src/components/EmptyState.tsx
import type { ReactNode } from "react";

interface EmptyStateProps {
  icon: string; // Emoji, z.B. "🚀"
  title: string;
  description: string;
  action?: ReactNode; // z.B. ein <Link>/<button> - bewusst als ReactNode statt
  // fixer Label/onClick-Props, damit sowohl <Link to="..."> (Navigation)
  // als auch <button onClick={...}> (z.B. "Formular öffnen") passen.
}

/** Verspielter Platzhalter für leere Listen/Zustände - siehe Design-Spec
 * "UX-Politur" Abschnitt 3. Ersetzt die bisherigen ad-hoc
 * "Noch nichts hier"-Absätze pro Seite durch eine einheitliche Optik. */
export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-white/10 bg-surface/40 px-6 py-12 text-center">
      <span className="text-4xl">{icon}</span>
      <p className="text-base font-semibold text-white">{title}</p>
      <p className="max-w-sm text-sm text-slate-400">{description}</p>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
