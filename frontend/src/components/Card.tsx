// frontend/src/components/Card.tsx
import type { ReactNode } from "react";

interface CardProps {
  title?: ReactNode;
  description?: string;
  children: ReactNode;
  className?: string;
  danger?: boolean; // roter Rahmen statt Standard - für die Danger Zone
}

/** Einheitlicher Abschnitts-Container mit optionaler Überschrift/
 * Beschreibung - siehe Design-Spec "UX-Politur" Abschnitt 2. Ersetzt die
 * bisher pro Sektion wiederholten `rounded-xl border ... bg-surface p-4`
 * + manuelle <h2>-Blöcke in Account.tsx. `title` akzeptiert seit dem
 * Check-in-Sichtbarkeits-Paket auch JSX (z.B. Titel + Zähler-Badge),
 * nicht mehr nur reinen Text. */
export function Card({ title, description, children, className = "", danger = false }: CardProps) {
  return (
    <div
      className={`rounded-xl border p-4 ${
        danger ? "border-red-900/40 bg-surface" : "border-white/5 bg-surface"
      } ${className}`}
    >
      {title && <h2 className="mb-1 text-lg font-semibold text-white">{title}</h2>}
      {description && <p className="mb-4 text-sm text-slate-400">{description}</p>}
      {children}
    </div>
  );
}
