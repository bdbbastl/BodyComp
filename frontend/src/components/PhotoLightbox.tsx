import { useEffect } from "react";
import { mediaUrl } from "../api/client";
import type { Photo } from "../types";
import { transformStyle, usePanZoom } from "../hooks/usePanZoom";
import { ZoomSlider } from "./ZoomSlider";

/** Vollbild-Layer für ein einzelnes Foto: Mausrad zum Zoomen, bei Zoom
 * Klick+Ziehen zum Verschieben (siehe usePanZoom), Escape/Backdrop-Klick/×
 * schließt. Ursprünglich nur in Timeline.tsx, jetzt gemeinsam mit
 * ClientCheckins.tsx genutzt (siehe Live-Feedback: Check-in-Fotos sollen
 * genauso aufrufbar/zoombar sein wie in der Timeline), nutzt dieselbe
 * Pan/Zoom-Logik wie Compare. */
export function PhotoLightbox({
  photo,
  label,
  onClose,
}: {
  photo: Photo;
  label: string;
  onClose: () => void;
}) {
  const { scale, translate, containerRef, isDragging, reset, setScaleFromSlider } = usePanZoom();

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-3 bg-black/90 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <button
        onClick={onClose}
        aria-label="Close"
        className="absolute right-4 top-4 flex h-10 w-10 items-center justify-center rounded-full bg-white/10 text-xl text-white hover:bg-white/20"
      >
        ✕
      </button>
      <div
        ref={containerRef}
        className="relative max-h-[80vh] w-full max-w-xl overflow-hidden rounded-xl bg-black"
        style={{ aspectRatio: "3 / 4", cursor: scale > 1 ? (isDragging ? "grabbing" : "grab") : "zoom-in" }}
        onDoubleClick={reset}
        title="Scroll to zoom, click+drag to pan while zoomed, double-click to reset"
      >
        <img
          src={mediaUrl(photo.display_path)}
          alt={label}
          draggable={false}
          className="h-full w-full object-contain"
          style={transformStyle(translate, scale)}
        />
        {scale > 1 && (
          <span className="pointer-events-none absolute bottom-1 right-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-slate-200">
            {scale.toFixed(1)}×
          </span>
        )}
      </div>
      <p className="text-sm text-slate-300">{label}</p>
      <div className="w-full max-w-xl rounded-xl border border-white/5 bg-surface p-4">
        <ZoomSlider scale={scale} onChange={setScaleFromSlider} />
      </div>
    </div>
  );
}
