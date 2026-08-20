// frontend/src/components/CompareExportModal.tsx
import { useEffect, useRef, useState } from "react";
import type { ExportAspect } from "../utils/compareExport";
import { dimensionsFor } from "../utils/compareExport";

/** Vorschau-Dialog vor dem eigentlichen Download - siehe Design-Spec
 * "Compare-Export für Social Media". `render` zeichnet auf den
 * übergebenen Canvas für das gewählte Format; wird bei jedem
 * Format-Wechsel erneut aufgerufen. */
export function CompareExportModal({
  onClose,
  render,
  filename,
}: {
  onClose: () => void;
  render: (canvas: HTMLCanvasElement, aspect: ExportAspect) => void;
  filename: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [aspect, setAspect] = useState<ExportAspect>("1:1");

  useEffect(() => {
    if (canvasRef.current) render(canvasRef.current, aspect);
  }, [aspect, render]);

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

  const dims = dimensionsFor(aspect);

  return (
    <div
      className="fixed inset-0 z-[90] flex items-center justify-center bg-black/70 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-lg rounded-xl border border-white/10 bg-surface p-6 shadow-2xl">
        <h2 className="mb-4 text-lg font-semibold text-white">Export Comparison</h2>

        <div className="mb-4 flex gap-2">
          <button
            type="button"
            onClick={() => setAspect("1:1")}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
              aspect === "1:1" ? "bg-accent text-slate-900" : "border border-white/15 text-white"
            }`}
          >
            1:1 (Instagram)
          </button>
          <button
            type="button"
            onClick={() => setAspect("4:3")}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
              aspect === "4:3" ? "bg-accent text-slate-900" : "border border-white/15 text-white"
            }`}
          >
            4:3
          </button>
        </div>

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
