/**
 * Nummerierte Pose-Labels ("1 - Front Relaxed", "2 - ...") für Dropdowns -
 * macht es leichter, Posen im Grid/den Fotos schnell per Auge zuzuordnen
 * (z.B. "Pose 3" statt sich den vollen Namen merken zu müssen).
 *
 * <option>-Elemente rendern nur Plain-Text, kein HTML/CSS - "hervorheben"
 * geht dort also nicht über <strong>/<span>. Als Ersatz: Keycap-Emoji-
 * Ziffern (1️⃣2️⃣3️⃣...) bilden optisch ein kleines "Badge" um die Zahl,
 * funktionieren aber als reiner Unicode-Text in jedem <option>. Für
 * mehrstellige Zahlen (ab 10) werden die Ziffern-Keycaps aneinandergereiht
 * (z.B. "1️⃣0️⃣" für 10) - kein einzelnes 10er-Symbol, aber konsistent mit
 * dem Muster für alle Zahlen bis 20 (max. Pose-Anzahl).
 */
function keycapDigit(digit: number): string {
  return `${digit}️⃣`;
}

export function keycapNumber(n: number): string {
  return String(n)
    .split("")
    .map((ch) => keycapDigit(Number(ch)))
    .join("");
}

/** Label für <option>-Elemente (Compare/Timeline-Dropdowns). */
export function numberedPoseOptionLabel(index: number, name: string): string {
  return `${keycapNumber(index + 1)} ${name}`;
}
