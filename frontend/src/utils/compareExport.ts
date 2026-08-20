// frontend/src/utils/compareExport.ts
import type { CurrentUser } from "../api/client";

export interface PaneExportState {
  scale: number;
  translateX: number;
  translateY: number;
  rotation: number;
  brightness: number;
}

export interface SliderExportState {
  scale: number;
  translateX: number;
  translateY: number;
  dividerPct: number;
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
 * gemeinsam genutzt von renderSideBySide und renderSlider. slotWidth/
 * slotHeight sind die Zielgröße der Region (z.B. eine Bildhälfte),
 * (offsetXPx, offsetYPx) die obere linke Ecke der Region auf dem
 * Gesamt-Canvas. */
function drawPhotoIntoRegion(
  ctx: CanvasRenderingContext2D,
  img: HTMLImageElement,
  region: { x: number; y: number; width: number; height: number },
  state: { scale: number; translateX: number; translateY: number; rotation: number; brightness: number }
): void {
  ctx.save();
  ctx.beginPath();
  ctx.rect(region.x, region.y, region.width, region.height);
  ctx.clip();

  ctx.filter = state.brightness === 100 ? "none" : `brightness(${state.brightness}%)`;

  // object-cover-Skalierung: Bild füllt die Zielregion vollständig aus,
  // überschüssige Ränder werden vom Clip oben abgeschnitten.
  const coverScale = Math.max(region.width / img.naturalWidth, region.height / img.naturalHeight);
  const drawWidth = img.naturalWidth * coverScale * state.scale;
  const drawHeight = img.naturalHeight * coverScale * state.scale;
  const centerX = region.x + region.width / 2 + state.translateX;
  const centerY = region.y + region.height / 2 + state.translateY;

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
  ctx.fillStyle = "rgba(255, 255, 255, 0.55)";
  ctx.textAlign = "right";
  ctx.textBaseline = "bottom";
  ctx.fillText("BodyComp Tracker", canvasWidth - 16, canvasHeight - 14);
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
  });
  ctx.restore();

  drawDivider(ctx, dividerX, height);
  if (showWatermark) drawWatermark(ctx, width, height);
}
