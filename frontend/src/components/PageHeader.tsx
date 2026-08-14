import type { ReactNode } from "react";

/** Einheitliche Seiten-Überschrift für alle eingeloggten Seiten
 * (Dashboard, Account, alle Kunden-Unterseiten) - siehe Design-Spec
 * Abschnitt "Gemeinsamer Seiten-Header & Abstände". Ersetzt die bisher
 * pro Seite leicht unterschiedlich gebauten <h1>-Blöcke. */
export default function PageHeader({
  title,
  actions,
}: {
  title: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex items-center justify-between">
      <h1 className="text-xl font-semibold text-white">{title}</h1>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
