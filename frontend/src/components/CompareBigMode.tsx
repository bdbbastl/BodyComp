// frontend/src/components/CompareBigMode.tsx
import { useEffect, useRef } from "react";
import { ChevronLeft, ChevronRight, X } from "lucide-react";

/**
 * Vollbild-Vorschau des aktuellen Vergleichs - siehe Design-Spec
 * "Compare: Adaptives Seitenverhältnis & Big Mode". Zeigt den
 * AKTUELLEN Stand (Zoom/Pan/Neigung/Belichtung/Format), verändert
 * nichts selbst; einzige Interaktion ist die Posen-Navigation über die
 * Pfeile hier oder die globale Pfeiltasten-Steuerung (siehe goToPose in
 * Compare.tsx - läuft unabhängig weiter, Big Mode fängt keinen Fokus).
 *
 * `render` ist derselbe Render-Pfad wie der Export (siehe
 * Compare.tsx renderComparisonToCanvas), nur mit showWatermark=false
 * und bildschirmfüllenden statt fest vorgegebenen Zielmaßen - Live-
 * Vorschau, Big Mode und Export zeigen dadurch garantiert dieselbe
 * Geometrie.
 */
export function CompareBigMode({
  aspectRatio,
  mode,
  render,
  poseLabel,
  onNavigate,
  onClose,
}: {
  /** Seitenverhältnis EINES Fotos/Panes (dasselbe, das ZoomPane/
   * SliderComparePane als aspectRatio bekommen) - NICHT das der
   * Gesamt-Canvas. */
  aspectRatio: number;
  mode: "side-by-side" | "slider";
  render: (canvas: HTMLCanvasElement, dims: { width: number; height: number }) => void;
  poseLabel: string;
  onNavigate: (delta: number) => void;
  onClose: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // renderSideBySideToCanvas teilt die Zielbreite intern durch 2 (zwei
  // Fotos nebeneinander) - die Gesamt-Canvas muss deshalb doppelt so
  // breit wie EIN Pane sein, damit jede Hälfte am Ende wieder exakt
  // `aspectRatio` hat. renderSliderToCanvas nutzt dagegen die ganze
  // Canvas als EINE gemeinsame Region für beide (überlagerten) Fotos -
  // dort entspricht die Canvas-Form direkt der Pane-Form. Ohne diese
  // Unterscheidung zeigte Big Mode im Side-by-Side-Modus jedes Foto nur
  // halb so breit wie das gewählte Seitenverhältnis (Bug-Report vom
  // User, per Test bestätigt: exakt Faktor 2 zu schmal).
  const canvasAspectRatio = mode === "side-by-side" ? aspectRatio * 2 : aspectRatio;

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  useEffect(() => {
    function draw() {
      const canvas = canvasRef.current;
      if (!canvas) return;
      // Größtmögliche Fläche innerhalb des verfügbaren Bereichs
      // (Viewport abzüglich Kopfleiste + Rand), die aspectRatio exakt
      // einhält - analog zu object-fit: contain, aber als konkrete
      // Canvas-Auflösung statt CSS-Skalierung, damit das Ergebnis nicht
      // unscharf hochskaliert wird.
      const availableWidth = window.innerWidth - 64;
      const availableHeight = window.innerHeight - 96;
      let width = availableWidth;
      let height = width / canvasAspectRatio;
      if (height > availableHeight) {
        height = availableHeight;
        width = height * canvasAspectRatio;
      }
      render(canvas, { width: Math.round(width), height: Math.round(height) });
    }
    draw();
    window.addEventListener("resize", draw);
    return () => window.removeEventListener("resize", draw);
  }, [render, canvasAspectRatio]);

  return (
    <div className="fixed inset-0 z-[95] flex flex-col items-center bg-black/90 p-4">
      <div className="mb-3 flex w-full max-w-4xl items-center justify-between">
        <button
          type="button"
          onClick={() => onNavigate(-1)}
          aria-label="Previous pose"
          className="flex h-10 w-10 items-center justify-center rounded-full bg-white/10 text-white hover:bg-white/20"
        >
          <ChevronLeft className="h-5 w-5" />
        </button>
        <span className="text-sm font-medium text-slate-200">{poseLabel}</span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onNavigate(1)}
            aria-label="Next pose"
            className="flex h-10 w-10 items-center justify-center rounded-full bg-white/10 text-white hover:bg-white/20"
          >
            <ChevronRight className="h-5 w-5" />
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="flex h-10 w-10 items-center justify-center rounded-full bg-white/10 text-white hover:bg-white/20"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
      </div>
      <canvas ref={canvasRef} className="max-h-full max-w-full rounded-xl" />
    </div>
  );
}
