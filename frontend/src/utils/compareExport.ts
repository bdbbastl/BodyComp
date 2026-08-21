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

export interface TargetDimensions {
  width: number;
  height: number;
}

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

const EXPORT_DIMENSIONS: Record<ExportAspect, TargetDimensions> = {
  "1:1": { width: 1080, height: 1080 },
  "4:3": { width: 1200, height: 900 },
};

export function dimensionsFor(aspect: ExportAspect): TargetDimensions {
  return EXPORT_DIMENSIONS[aspect];
}

/** Verallgemeinerte Variante von dimensionsFor: nimmt entweder eines der
 * beiden benannten Export-Formate ODER beliebige Zielmaße direkt
 * entgegen. Genutzt von Big Mode, das keine feste Export-Form hat,
 * sondern die live gewählte Container-Form bildschirmfüllend zeigt -
 * derselbe Render-Pfad wie der Export, nur mit anderer Zielgröße. */
export function resolveDimensions(target: ExportAspect | TargetDimensions): TargetDimensions {
  if (typeof target === "string") return dimensionsFor(target);
  return target;
}

/**
 * Vollständiger Live-Transform-Zustand einer Vergleichs-Kachel.
 *
 * Entspricht 1:1 dem DOM in Compare.tsx:
 *
 *   <div ref={containerRef} class="aspect-[3/4] overflow-hidden">   // W × H CSS-Pixel
 *     <div style={transformStyle(translate, scale)}>                // translate(t) scale(s), origin "0 0"
 *       <img class="h-full w-full object-cover"
 *            style="transform: translate(o) scale(fz) rotate(r)" /> // origin 50% 50%
 *
 * `offsetX/offsetY/fineZoom` gibt es nur im Slider-Modus (Feinjustierung
 * pro Bild); im Side-by-Side-Modus sind sie 0 bzw. 1.
 */
export interface LivePaneTransform {
  scale: number;
  translateX: number;
  translateY: number;
  offsetX: number;
  offsetY: number;
  fineZoom: number;
  rotation: number;
  containerWidth: number;
  containerHeight: number;
}

/** Bildet den Live-Container auf eine Export-Region ab: eine Box mit
 * demselben Seitenverhältnis wie der Container, die die Region
 * vollständig überdeckt ("cover" - was übersteht, schneidet der Clip in
 * drawPhotoIntoRegion ab; bewusst kein Letterboxing). `k` ist der
 * einheitliche Vergrößerungsfaktor Live-CSS-Pixel -> Export-Pixel. */
export function mapContainerToRegion(
  region: { x: number; y: number; width: number; height: number },
  containerWidth: number,
  containerHeight: number
): { x: number; y: number; width: number; height: number; k: number } {
  const containerAspect = containerWidth / containerHeight;
  let width = region.width;
  let height = width / containerAspect;
  if (height < region.height) {
    height = region.height;
    width = height * containerAspect;
  }
  return {
    x: region.x + (region.width - width) / 2,
    y: region.y + (region.height - height) / 2,
    width,
    height,
    k: width / containerWidth,
  };
}

/** Wo das Foto in der LIVE-Vorschau liegt - Mittelpunkt und Größe in
 * CSS-Pixeln relativ zur linken oberen Container-Ecke.
 *
 * Für einen Punkt n des Originalfotos (relativ zu dessen Mitte) gilt in
 * der Live-Vorschau:
 *
 *   screen = scale * (C + offset) + translate  +  scale * fineZoom * coverScale * R(rot) * n
 *            └────── Bildmitte ──────────────┘     └───── effektiver Maßstab ─────┘
 *
 * mit C = (containerWidth/2, containerHeight/2).
 *
 * ACHTUNG - hier lag der Bug: `transform-origin` des äußeren Divs ist
 * explizit "0 0" (siehe usePanZoom.transformStyle), der Ursprung sitzt
 * also in der ECKE des Containers, nicht in seiner Mitte. Deshalb
 * skaliert `scale` auch die Bildmitte C und den Bild-Offset - nicht nur
 * die Bildgröße. Frühere Fassungen behandelten `translate` als reinen
 * Versatz von der Regionsmitte; dadurch lag jede gezoomte Kachel um
 * (scale-1)*C daneben. Bei scale=1 war das unsichtbar (Fehler = 0), bei
 * Zoom 1.4 wanderte das Bild sichtbar nach oben aus der Region heraus -
 * abgeschnittener Kopf, schwarzer Balken am unteren Rand. */
export function liveImagePlacement(
  naturalWidth: number,
  naturalHeight: number,
  t: LivePaneTransform
): { centerX: number; centerY: number; width: number; height: number; rotation: number } {
  const coverScale = Math.max(t.containerWidth / naturalWidth, t.containerHeight / naturalHeight);
  const drawScale = coverScale * t.scale * t.fineZoom;
  return {
    centerX: t.scale * (t.containerWidth / 2 + t.offsetX) + t.translateX,
    centerY: t.scale * (t.containerHeight / 2 + t.offsetY) + t.translateY,
    width: naturalWidth * drawScale,
    height: naturalHeight * drawScale,
    rotation: t.rotation,
  };
}

/** Zeichnet ein einzelnes Foto mit seinem aktuellen Zoom/Pan/Rotation/
 * Belichtung-Zustand in eine rechteckige Zielregion des Canvas -
 * gemeinsam genutzt von renderSideBySide und renderSlider. Der Export ist
 * damit eine reine, gleichmäßige Vergrößerung der Live-Vorschau um den
 * Faktor k. */
function drawPhotoIntoRegion(
  ctx: CanvasRenderingContext2D,
  img: HTMLImageElement,
  region: { x: number; y: number; width: number; height: number },
  t: LivePaneTransform,
  brightness: number
): void {
  ctx.save();
  ctx.beginPath();
  ctx.rect(region.x, region.y, region.width, region.height);
  ctx.clip();

  ctx.filter = brightness === 100 ? "none" : `brightness(${brightness}%)`;

  const box = mapContainerToRegion(region, t.containerWidth, t.containerHeight);
  const live = liveImagePlacement(img.naturalWidth, img.naturalHeight, t);

  const drawWidth = live.width * box.k;
  const drawHeight = live.height * box.k;

  ctx.translate(box.x + live.centerX * box.k, box.y + live.centerY * box.k);
  ctx.rotate((live.rotation * Math.PI) / 180);
  ctx.drawImage(img, -drawWidth / 2, -drawHeight / 2, drawWidth, drawHeight);

  ctx.restore();
}

/** Side-by-Side: die Kachel hat keine Feinjustierung pro Bild - nur den
 * Pan/Zoom des Containers und die Neigung. */
function paneTransform(state: PaneExportState): LivePaneTransform {
  return {
    scale: state.scale,
    translateX: state.translateX,
    translateY: state.translateY,
    offsetX: 0,
    offsetY: 0,
    fineZoom: 1,
    rotation: state.rotation,
    containerWidth: state.containerWidth,
    containerHeight: state.containerHeight,
  };
}

/** Slider: Pan/Zoom des Containers gilt für BEIDE Bilder gemeinsam, der
 * Versatz/Feinzoom liegt zusätzlich auf dem jeweiligen <img> - also eine
 * Ebene weiter innen, innerhalb des gemeinsamen scale. */
function sliderTransform(
  state: SliderExportState,
  side: SliderExportState["x"]
): LivePaneTransform {
  return {
    scale: state.scale,
    translateX: state.translateX,
    translateY: state.translateY,
    offsetX: side.offsetX,
    offsetY: side.offsetY,
    fineZoom: side.fineZoom,
    rotation: side.rotation,
    containerWidth: state.containerWidth,
    containerHeight: state.containerHeight,
  };
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
  target: ExportAspect | TargetDimensions,
  imgX: HTMLImageElement,
  stateX: PaneExportState,
  imgY: HTMLImageElement,
  stateY: PaneExportState,
  showWatermark: boolean
): void {
  const { width, height } = resolveDimensions(target);
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  ctx.fillStyle = "#0b0f14";
  ctx.fillRect(0, 0, width, height);

  const halfWidth = width / 2;
  drawPhotoIntoRegion(ctx, imgX, { x: 0, y: 0, width: halfWidth, height }, paneTransform(stateX), stateX.brightness);
  drawPhotoIntoRegion(ctx, imgY, { x: halfWidth, y: 0, width: halfWidth, height }, paneTransform(stateY), stateY.brightness);
  drawDivider(ctx, halfWidth, height);

  if (showWatermark) drawWatermark(ctx, width, height);
}

export function renderSliderToCanvas(
  canvas: HTMLCanvasElement,
  target: ExportAspect | TargetDimensions,
  imgX: HTMLImageElement,
  imgY: HTMLImageElement,
  state: SliderExportState,
  showWatermark: boolean
): void {
  const { width, height } = resolveDimensions(target);
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  ctx.fillStyle = "#0b0f14";
  ctx.fillRect(0, 0, width, height);

  const sharedRegion = { x: 0, y: 0, width, height };

  // Bild Y als volle Basis-Ebene (wie in der Live-Vorschau).
  drawPhotoIntoRegion(ctx, imgY, sharedRegion, sliderTransform(state, state.y), state.y.brightness);

  // Bild X darüber, auf den linken Divider-Anteil begrenzt.
  const dividerX = (state.dividerPct / 100) * width;
  ctx.save();
  ctx.beginPath();
  ctx.rect(0, 0, dividerX, height);
  ctx.clip();
  drawPhotoIntoRegion(ctx, imgX, sharedRegion, sliderTransform(state, state.x), state.x.brightness);
  ctx.restore();

  drawDivider(ctx, dividerX, height);
  if (showWatermark) drawWatermark(ctx, width, height);
}
