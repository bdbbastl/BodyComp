// frontend/src/components/Avatar.tsx
const AVATAR_COLORS = [
  "bg-cyan-500/20 text-cyan-300",
  "bg-violet-500/20 text-violet-300",
  "bg-amber-500/20 text-amber-300",
  "bg-emerald-500/20 text-emerald-300",
  "bg-pink-500/20 text-pink-300",
  "bg-blue-500/20 text-blue-300",
];

/** Deterministisch aus dem Namen abgeleiteter Farbindex, damit derselbe
 * Klient überall im UI dieselbe Avatar-Farbe hat (keine zufällige Farbe
 * pro Render). */
function colorClassFor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  }
  return AVATAR_COLORS[hash % AVATAR_COLORS.length];
}

function initialsFor(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** Initialen-Avatar für Klienten ohne eigenes Profilbild-Feature - siehe
 * Design-Spec "Dashboard & Landing-Page Visual Refresh" Abschnitt 3. */
export function Avatar({ name, size = 24 }: { name: string; size?: number }) {
  return (
    <div
      className={`flex shrink-0 items-center justify-center rounded-full text-[10px] font-semibold ${colorClassFor(name)}`}
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      {initialsFor(name)}
    </div>
  );
}
