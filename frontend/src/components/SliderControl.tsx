import { useState } from "react";
import type { ReactNode } from "react";

/**
 * Gemeinsamer Baustein für alle Feinjustierungs-Regler auf der Compare-
 * Seite (Zoom, Rotation, Position, Belichtung, Overlay-Deckkraft).
 *
 * Aufbau bewusst zweizeilig für ein ruhiges, konsistentes Desktop-UI statt
 * einer überladenen Einzeilen-Reihe aus Icon+Buttons+Slider+Zahl+Einheit:
 *   Zeile 1: Label links, editierbarer Wert (+ Einheit) rechts
 *   Zeile 2: [−] Regler [+]
 * Der Wert in Zeile 1 IST das Eingabefeld (kein zusätzliches, separates
 * Zahlenfeld) - dezent gestaltet (kein Rahmen bis zum Fokus), damit er
 * wie ein Live-Messwert wirkt und trotzdem direkt per Tastatur editierbar
 * bleibt.
 */
export function SliderControl({
  icon,
  label,
  value,
  min,
  max,
  step,
  onChange,
  suffix = "",
  decimals = 0,
}: {
  icon?: ReactNode;
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
  suffix?: string;
  /** Nachkommastellen für Rundung nach +/- Klick und Anzeige (vermeidet
   * Fließkomma-Reste wie 1.2000000000000002). */
  decimals?: number;
}) {
  // Eigener Text-State fürs Zahlenfeld, damit man z.B. "1." oder "-" beim
  // Tippen zwischendurch eingeben kann, ohne dass der Wert sofort gegen
  // `value` validiert und zurückgesetzt wird.
  const [draft, setDraft] = useState<string | null>(null);

  function clamp(v: number): number {
    return Math.min(max, Math.max(min, v));
  }
  function round(v: number): number {
    const factor = 10 ** decimals;
    return Math.round(v * factor) / factor;
  }
  function bump(delta: number) {
    onChange(clamp(round(value + delta)));
  }
  function commitDraft(raw: string) {
    const parsed = Number(raw);
    if (raw.trim() !== "" && !Number.isNaN(parsed)) {
      onChange(clamp(round(parsed)));
    }
    setDraft(null);
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-xs font-medium text-slate-400">
          {icon && <span className="text-sm leading-none opacity-80">{icon}</span>}
          {label}
        </span>
        <div className="flex items-center gap-0.5">
          <input
            type="number"
            min={min}
            max={max}
            step={step}
            value={draft ?? (decimals > 0 ? value.toFixed(decimals) : String(value))}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={(e) => commitDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") e.currentTarget.blur();
            }}
            className="w-14 rounded border border-transparent bg-transparent py-0.5 text-right font-mono text-sm tabular-nums text-slate-200 transition-colors hover:border-white/10 hover:bg-black/20 focus:border-accent focus:bg-black/30 focus:outline-none"
          />
          {suffix && <span className="text-xs text-slate-500">{suffix}</span>}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => bump(-step)}
          aria-label={`Decrease ${label}`}
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-slate-400 transition-colors hover:bg-white/10 hover:text-white active:bg-white/15"
        >
          <span className="text-base leading-none">−</span>
        </button>
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          aria-label={label}
          className="h-1.5 flex-1 accent-accent"
        />
        <button
          type="button"
          onClick={() => bump(step)}
          aria-label={`Increase ${label}`}
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-slate-400 transition-colors hover:bg-white/10 hover:text-white active:bg-white/15"
        >
          <span className="text-base leading-none">+</span>
        </button>
      </div>
    </div>
  );
}
