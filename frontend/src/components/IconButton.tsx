import type { LucideIcon } from "lucide-react";
import { Loader2 } from "lucide-react";

/**
 * Icon-Button ohne sichtbares Textlabel - genutzt im Compare-Header
 * (Ansichtsschalter + Aktionen) und in der Reglerleiste unter jedem Foto.
 *
 * `label` ist bewusst ein Pflicht-Prop und NICHT optional: Der Button
 * zeigt keinen Text, also ist das Label die einzige Beschriftung für
 * Screenreader und der einzige Tooltip für sehende Nutzer.
 */
export function IconButton({
  icon: Icon,
  label,
  onClick,
  variant = "ghost",
  active = false,
  pending = false,
  disabled = false,
  toggle = false,
  dot = false,
  badge,
  size = "md",
}: {
  icon: LucideIcon;
  /** Pflicht - wird aria-label UND title. */
  label: string;
  onClick?: () => void;
  variant?: "ghost" | "accent";
  /** Toggle ist eingeschaltet bzw. Werkzeug ist ausgewählt. */
  active?: boolean;
  /** Zeigt einen Spinner und sperrt den Button. */
  pending?: boolean;
  disabled?: boolean;
  /** Setzt aria-pressed - nur für echte An/Aus-Schalter. */
  toggle?: boolean;
  /** Kleiner Akzentpunkt oben rechts: Wert weicht vom Standard ab. */
  dot?: boolean;
  /** Zahl oben rechts, z.B. Anzahl Posen bei "All poses". */
  badge?: number;
  size?: "sm" | "md";
}) {
  const box = size === "sm" ? "h-8 w-8" : "h-9 w-9";
  const glyph = size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4";

  const tone =
    variant === "accent"
      ? "border-accent bg-accent text-slate-900 hover:opacity-90"
      : active || pending
        ? "border-accent/40 bg-accent/10 text-accent hover:bg-accent/20"
        : "border-white/10 bg-white/5 text-slate-300 hover:bg-white/10 hover:text-white";

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || pending}
      aria-label={label}
      title={label}
      aria-pressed={toggle ? active : undefined}
      className={`relative inline-flex shrink-0 items-center justify-center rounded-lg border transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-35 ${box} ${tone}`}
    >
      {pending ? <Loader2 className={`${glyph} animate-spin`} /> : <Icon className={glyph} />}
      {dot && !pending && (
        <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full border-2 border-surface bg-accent" />
      )}
      {badge !== undefined && !pending && (
        <span className="absolute -right-1.5 -top-1.5 rounded-full border border-accent bg-background px-1 text-[9px] font-bold leading-4 text-accent">
          {badge}
        </span>
      )}
    </button>
  );
}
