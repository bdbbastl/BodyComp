// frontend/src/utils/compareAspect.ts
import type { Photo } from "../types";

/**
 * Seitenverhältnis der Compare-Container - siehe Design-Spec "Compare:
 * Adaptives Seitenverhältnis & Big Mode". "auto" berechnet die Form aus
 * den echten Pixelmaßen beider verglichener Fotos; die übrigen Werte
 * sind manuelle Presets, die die Automatik überschreiben.
 */
export type AspectPreset = "auto" | "3:4" | "4:5" | "1:1" | "9:16";

export const ASPECT_PRESETS: Record<Exclude<AspectPreset, "auto">, number> = {
  "3:4": 3 / 4,
  "4:5": 4 / 5,
  "1:1": 1,
  "9:16": 9 / 16,
};

// Heutiges Verhalten (fest 3:4), falls Fotomaße fehlen (alte, nicht
// nachgetragene Datensätze - siehe backend/app/services/folder_sync.py).
const FALLBACK_RATIO = 3 / 4;

// Die Auto-Berechnung wird nie extremer als die weiteste bzw. schmalste
// manuelle Preset-Option - verhindert, dass ein falsch rotiertes oder
// extrem verzerrtes Foto die Box absurd verformt. "1:1" ist jetzt die
// breiteste Preset-Option, also auch die neue Obergrenze.
const AUTO_MIN_RATIO = ASPECT_PRESETS["9:16"];
const AUTO_MAX_RATIO = ASPECT_PRESETS["1:1"];

type PhotoDimensions = Pick<Photo, "width" | "height">;

/** Seitenverhältnis (Breite/Höhe) beider Fotos, das kleinere gewinnt -
 * das hochkantigere Foto bestimmt die Form, das andere verliert
 * höchstens Rand links/rechts, nie Kopf oder Füße. Auf den erlaubten
 * Bereich geklemmt. Fehlen die Maße bei einem der beiden Fotos, gilt
 * der Fallback. */
export function computeAutoAspectRatio(
  photoX: PhotoDimensions | undefined,
  photoY: PhotoDimensions | undefined
): number {
  if (!photoX?.width || !photoX?.height || !photoY?.width || !photoY?.height) {
    return FALLBACK_RATIO;
  }
  const ratioX = photoX.width / photoX.height;
  const ratioY = photoY.width / photoY.height;
  const ratio = Math.min(ratioX, ratioY);
  return Math.min(AUTO_MAX_RATIO, Math.max(AUTO_MIN_RATIO, ratio));
}

/** Löst den gewählten Preset in ein konkretes Seitenverhältnis auf. Bei
 * einem manuellen Preset wird der feste Wert unverändert zurückgegeben
 * (eine bewusste Nutzerwahl wird nicht geklemmt); bei "auto" greift
 * computeAutoAspectRatio. */
export function resolveAspectRatio(
  preset: AspectPreset,
  photoX: PhotoDimensions | undefined,
  photoY: PhotoDimensions | undefined
): number {
  if (preset !== "auto") return ASPECT_PRESETS[preset];
  return computeAutoAspectRatio(photoX, photoY);
}
