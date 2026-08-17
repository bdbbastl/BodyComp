// frontend/src/components/Skeleton.tsx

/** Schmaler pulsierender Balken - für einzelne Textzeilen-Platzhalter. */
export function SkeletonLine({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-white/10 ${className}`} />;
}

/** Karten-förmiger Platzhalter (Bild oben, Zeilen darunter) - für
 * Listen-/Grid-Ansichten wie Dashboard-Klientenkarten oder Timeline-Fotos,
 * siehe Design-Spec "UX-Politur" Abschnitt 4. */
export function SkeletonCard() {
  return (
    <div className="animate-pulse overflow-hidden rounded-xl border border-white/5 bg-surface p-4">
      <div className="mb-3 h-4 w-2/3 rounded bg-white/10" />
      <div className="mb-2 h-3 w-1/2 rounded bg-white/5" />
      <div className="h-3 w-1/3 rounded bg-white/5" />
    </div>
  );
}

/** Mehrere SkeletonCards im Grid, deckt einen typischen Lade-Zustand ab
 * (z.B. Dashboard-Klientenliste beim ersten Laden). */
export function SkeletonGrid({ count = 6 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}
