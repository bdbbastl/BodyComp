// frontend/src/components/CompareExportModal.tsx
import { useEffect, useRef } from "react";
import { exportDimensionsForRatio } from "../utils/compareExport";

/** Vorschau-Dialog vor dem eigentlichen Download - siehe Design-Spec
 * "Compare-Export für Social Media". Nutzt bewusst KEINE eigene
 * Format-Auswahl mehr (früher 1:1/4:3, unabhängig von der Live-
 * Vorschau) - der Export übernimmt exakt das Format, das gerade auf
 * der Compare-Seite gewählt ist (Auto/3:4/4:5/1:1/9:16, siehe
 * CompareFilterBar), damit Live-Vorschau, Big Mode und Export niemals
 * unterschiedliche Ausschnitte zeigen können (User-Feedback: Export
 * brauchte "die gleichen Maße wie die Anzeige auf der Compare-Seite").
 * `render` zeichnet auf den übergebenen Canvas; wird erneut aufgerufen,
 * sobald sich die Zielmaße ändern (z.B. weil der User das Format auf
 * der Compare-Seite gewechselt hat, während dieses Modal offen ist). */
export function CompareExportModal({
  onClose,
  render,
  filename,
  aspectRatio,
}: {
  onClose: () => void;
  render: (canvas: HTMLCanvasElement, dims: { width: number; height: number }) => void;
  filename: string;
  /** Aktuell auf der Compare-Seite gewähltes/berechnetes Seitenverhältnis. */
  aspectRatio: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const dims = exportDimensionsForRatio(aspectRatio);

  useEffect(() => {
    if (canvasRef.current) render(canvasRef.current, dims);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dims.width, dims.height, render]);

  const handleDownload = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.toBlob((blob) => {
      if (!blob) return;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    }, "image/png");
  };

  return (
    <div
      className="fixed inset-0 z-[90] flex items-center justify-center bg-black/70 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-lg rounded-xl border border-white/10 bg-surface p-6 shadow-2xl">
        <h2 className="mb-1 text-lg font-semibold text-white">Export Comparison</h2>
        <p className="mb-4 text-xs text-slate-400">
          {dims.width} × {dims.height}px — matches the format selected on the Compare page
        </p>

        <div className="mb-4 flex justify-center overflow-hidden rounded-lg bg-black/40">
          <canvas
            ref={canvasRef}
            style={{ maxWidth: "100%", aspectRatio: `${dims.width} / ${dims.height}` }}
          />
        </div>

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-white/15 px-4 py-2 text-sm font-medium text-white hover:bg-white/5"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleDownload}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90"
          >
            Download
          </button>
        </div>
      </div>
    </div>
  );
}
