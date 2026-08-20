// frontend/src/components/Sparkline.tsx

/** Kleine Balken-Sparkline für Kennzahlen-Widgets - siehe Design-Spec
 * "Dashboard & Landing-Page Visual Refresh" Abschnitt 2. Rein
 * dekorativ/informativ, kein Hover/Tooltip (dafür gibt es die
 * ausführlichen Charts auf der Statistics-Seite). */
export function Sparkline({ values, height = 20 }: { values: number[]; height?: number }) {
  const max = Math.max(1, ...values);
  return (
    <div className="flex items-end gap-[3px]" style={{ height }} aria-hidden="true">
      {values.map((v, i) => {
        const isLast = i === values.length - 1;
        return (
          <div
            key={i}
            className={`w-[6px] rounded-sm ${isLast ? "bg-accent" : "bg-accent/35"}`}
            style={{ height: `${Math.max(8, (v / max) * 100)}%` }}
          />
        );
      })}
    </div>
  );
}
