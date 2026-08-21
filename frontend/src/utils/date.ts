/** ISO-8601-Kalenderwoche (Mo-So, Woche 1 enthält den ersten Donnerstag
 * des Jahres) - der in Deutschland übliche Wochenzähler. */
export function getISOWeek(date: Date): number {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const dayNum = d.getUTCDay() || 7; // Sonntag = 0 -> 7
  d.setUTCDate(d.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  return Math.ceil(((d.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
}

export function formatDateWithWeek(iso: string): string {
  const date = new Date(iso);
  const formatted = date.toLocaleDateString("en-US", {
    weekday: "short",
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
  return `${formatted} · Week ${getISOWeek(date)}`;
}

export function formatDateShortWithWeek(iso: string): string {
  const date = new Date(iso);
  const formatted = date.toLocaleDateString("en-US", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
  return `${formatted} · Week ${getISOWeek(date)}`;
}

/** Formatiert ein Date als lokales YYYY-MM-DD (für <input type="date">
 * value/max-Attribute) - bewusst NICHT über toISOString(), das würde ins
 * UTC-Datum konvertieren und nahe Mitternacht in vielen Zeitzonen auf
 * den falschen Tag springen. */
export function toIsoDateLocal(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}
