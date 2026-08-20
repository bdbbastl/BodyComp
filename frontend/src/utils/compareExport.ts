// frontend/src/utils/compareExport.ts
import type { CurrentUser } from "../api/client";

export interface PaneExportState {
  scale: number;
  translateX: number;
  translateY: number;
  rotation: number;
  brightness: number;
  containerWidth: number;
  containerHeight: number;
}

export interface SliderExportState {
  scale: number;
  translateX: number;
  translateY: number;
  dividerPct: number;
  containerWidth: number;
  containerHeight: number;
  x: { offsetX: number; offsetY: number; fineZoom: number; rotation: number; brightness: number };
  y: { offsetX: number; offsetY: number; fineZoom: number; rotation: number; brightness: number };
}

export type ExportAspect = "1:1" | "4:3";

/** Wasserzeichen-Regel - siehe Design-Spec "Compare-Export für Social
 * Media" Abschnitt "Sichtbarkeit / Wasserzeichen-Logik im Detail".
 * Nur zahlende Coaches sind befreit - Single-Accounts (auch mit
 * aktivem Plan) bekommen immer ein Wasserzeichen. */
export function shouldShowWatermark(user: Pick<CurrentUser, "account_type" | "subscription_status"> | undefined): boolean {
  if (!user) return true;
  const isPayingCoach =
    user.account_type === "coach" && ["active", "trialing"].includes(user.subscription_status ?? "");
  return !isPayingCoach;
}

export function exportFilename(clientName: string, dateX: string, dateY: string): string {
  const safeName = clientName.trim().replace(/\s+/g, "-");
  return `bodycomp-compare-${safeName}-${dateX}-vs-${dateY}.png`;
}

const EXPORT_DIMENSIONS: Record<ExportAspect, { width: number; height: number }> = {
  "1:1": { width: 1080, height: 1080 },
  "4:3": { width: 1200, height: 900 },
};

export function dimensionsFor(aspect: ExportAspect) {
  return EXPORT_DIMENSIONS[aspect];
}

/** Zeichnet ein einzelnes Foto mit seinem aktuellen Zoom/Pan/Rotation/
 * Belichtung-Zustand in eine rechteckige Zielregion des Canvas -
 * gemeinsam genutzt von renderSideBySide und renderSlider.
 *
 * Repliziert den exakten Crop der Live-Vorschau in zwei Schritten:
 * 1. Eine Box mit demselben Seitenverhältnis wie der TATSÄCHLICHE
 *    Live-Container (state.containerWidth/Height, live per
 *    getBoundingClientRect() gemessen - nicht angenommen) wird so groß
 *    wie nötig berechnet, um die Export-Region vollständig abzudecken
 *    ("cover", übersteht sie die Region in einer Richtung wird das vom
 *    Clip oben abgeschnitten - kein Letterboxing).
 * 2. state.translateX/Y sind Live-CSS-Pixel-Offsets aus dem tatsächlich
 *    gerenderten Container - da dieser Container fast immer eine andere
 *    Pixelgröße hat als die Export-Box (z.B. 320px live vs. 1000px+
 *    Export), werden sie mit demselben Skalierungsfaktor k
 *    (Export-Box-Breite / Live-Container-Breite) multipliziert, den
 *    auch die Bild-Skalierung selbst nutzt - sonst wäre der Pan im
 *    Export unproportional schwach/stark im Vergleich zur Live-Ansicht
 *    (Bug-Report vom User: Export zeigte einen komplett anderen, viel
 *    weniger gezoomten Ausschnitt als live sichtbar). */
function drawPhotoIntoRegion(
  ctx: CanvasRenderingContext2D,
  img: HTMLImageElement,
  region: { x: number; y: number; width: number; height: number },
  state: {
    scale: number;
    translateX: number;
    translateY: number;
    rotation: number;
    brightness: number;
    containerWidth: number;
    containerHeight: number;
  }
): void {
  ctx.save();
  ctx.beginPath();
  ctx.rect(region.x, region.y, region.width, region.height);
  ctx.clip();

  ctx.filter = state.brightness === 100 ? "none" : `brightness(${state.brightness}%)`;

  const containerAspect = state.containerWidth / state.containerHeight;
  let boxWidth = region.width;
  let boxHeight = boxWidth / containerAspect;
  if (boxHeight < region.height) {
    boxHeight = region.height;
    boxWidth = boxHeight * containerAspect;
  }
  const boxX = region.x + (region.width - boxWidth) / 2;
  const boxY = region.y + (region.height - boxHeight) / 2;

  // Skalierungsfaktor von Live-Container-Pixeln auf Export-Box-Pixel -
  // macht Pan-Offsets proportional korrekt, unabhängig davon, wie groß
  // der Live-Container gerade auf dem Bildschirm des Users war.
  const k = boxWidth / state.containerWidth;

  const coverScale = Math.max(boxWidth / img.naturalWidth, boxHeight / img.naturalHeight);
  const drawWidth = img.naturalWidth * coverScale * state.scale;
  const drawHeight = img.naturalHeight * coverScale * state.scale;
  const centerX = boxX + boxWidth / 2 + state.translateX * k;
  const centerY = boxY + boxHeight / 2 + state.translateY * k;

  ctx.translate(centerX, centerY);
  ctx.rotate((state.rotation * Math.PI) / 180);
  ctx.drawImage(img, -drawWidth / 2, -drawHeight / 2, drawWidth, drawHeight);

  ctx.restore();
}

function drawDivider(ctx: CanvasRenderingContext2D, x: number, canvasHeight: number): void {
  ctx.save();
  ctx.strokeStyle = "rgba(255, 255, 255, 0.85)";
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(x, 0);
  ctx.lineTo(x, canvasHeight);
  ctx.stroke();
  ctx.restore();
}

function drawWatermark(ctx: CanvasRenderingContext2D, canvasWidth: number, canvasHeight: number): void {
  ctx.save();
  ctx.font = "600 20px sans-serif";
  const text = "BodyComp Tracker";
  const paddingX = 10;
  const paddingY = 6;
  const textWidth = ctx.measureText(text).width;
  const chipHeight = 20 + paddingY * 2;
  const chipWidth = textWidth + paddingX * 2;
  const chipX = canvasWidth - 16 - chipWidth;
  const chipY = canvasHeight - 14 - chipHeight;

  // Dunkler, halbtransparenter Hintergrund-Chip hinter dem Text - reiner
  // heller Text allein war auf hellen Foto-Hintergründen (z.B. Wand/Boden)
  // praktisch unsichtbar (Bug-Report vom User). Der Chip macht das
  // Wasserzeichen unabhängig vom Foto-Untergrund lesbar.
  ctx.fillStyle = "rgba(0, 0, 0, 0.45)";
  ctx.beginPath();
  const radius = 6;
  ctx.moveTo(chipX + radius, chipY);
  ctx.arcTo(chipX + chipWidth, chipY, chipX + chipWidth, chipY + chipHeight, radius);
  ctx.arcTo(chipX + chipWidth, chipY + chipHeight, chipX, chipY + chipHeight, radius);
  ctx.arcTo(chipX, chipY + chipHeight, chipX, chipY, radius);
  ctx.arcTo(chipX, chipY, chipX + chipWidth, chipY, radius);
  ctx.closePath();
  ctx.fill();

  ctx.fillStyle = "rgba(255, 255, 255, 0.9)";
  ctx.textAlign = "right";
  ctx.textBaseline = "bottom";
  ctx.fillText(text, canvasWidth - 16 - paddingX, canvasHeight - 14 - paddingY);
  ctx.restore();
}

export function renderSideBySideToCanvas(
  canvas: HTMLCanvasElement,
  aspect: ExportAspect,
  imgX: HTMLImageElement,
  stateX: PaneExportState,
  imgY: HTMLImageElement,
  stateY: PaneExportState,
  showWatermark: boolean
): void {
  const { width, height } = dimensionsFor(aspect);
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  ctx.fillStyle = "#0b0f14";
  ctx.fillRect(0, 0, width, height);

  const halfWidth = width / 2;
  drawPhotoIntoRegion(ctx, imgX, { x: 0, y: 0, width: halfWidth, height }, stateX);
  drawPhotoIntoRegion(ctx, imgY, { x: halfWidth, y: 0, width: halfWidth, height }, stateY);
  drawDivider(ctx, halfWidth, height);

  if (showWatermark) drawWatermark(ctx, width, height);
}

export function renderSliderToCanvas(
  canvas: HTMLCanvasElement,
  aspect: ExportAspect,
  imgX: HTMLImageElement,
  imgY: HTMLImageElement,
  state: SliderExportState,
  showWatermark: boolean
): void {
  const { width, height } = dimensionsFor(aspect);
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  ctx.fillStyle = "#0b0f14";
  ctx.fillRect(0, 0, width, height);

  const sharedRegion = { x: 0, y: 0, width, height };
  const combineScale = (fineZoom: number) => state.scale * fineZoom;

  // Bild Y als volle Basis-Ebene (wie in der Live-Vorschau).
  drawPhotoIntoRegion(ctx, imgY, sharedRegion, {
    scale: combineScale(state.y.fineZoom),
    translateX: state.translateX + state.y.offsetX,
    translateY: state.translateY + state.y.offsetY,
    rotation: state.y.rotation,
    brightness: state.y.brightness,
    containerWidth: state.containerWidth,
    containerHeight: state.containerHeight,
  });

  // Bild X darüber, auf den linken Divider-Anteil begrenzt.
  const dividerX = (state.dividerPct / 100) * width;
  ctx.save();
  ctx.beginPath();
  ctx.rect(0, 0, dividerX, height);
  ctx.clip();
  drawPhotoIntoRegion(ctx, imgX, sharedRegion, {
    scale: combineScale(state.x.fineZoom),
    translateX: state.translateX + state.x.offsetX,
    translateY: state.translateY + state.x.offsetY,
    rotation: state.x.rotation,
    brightness: state.x.brightness,
    containerWidth: state.containerWidth,
    containerHeight: state.containerHeight,
  });
  ctx.restore();

  drawDivider(ctx, dividerX, height);
  if (showWatermark) drawWatermark(ctx, width, height);
}
