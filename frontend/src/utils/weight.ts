/** Parst eine Gewichts-Nutzereingabe (Komma ODER Punkt als
 * Dezimaltrennzeichen, z.B. "76,05" oder "76.05") zu einer Zahl,
 * gerundet auf die naechsten 0,05 kg - siehe Design-Spec
 * "Usability-Fixes Runde 2" Abschnitt 2. Gibt null bei leerem Input
 * zurueck (== "kein Wert eingegeben"), NaN bei tatsaechlich ungueltigem
 * Input (Aufrufer soll das von "kein Wert" unterscheiden koennen). */
export function parseWeightInput(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  const normalized = trimmed.replace(",", ".");
  const value = Number(normalized);
  if (!Number.isFinite(value)) return NaN;
  return Math.round(value / 0.05) * 0.05;
}
