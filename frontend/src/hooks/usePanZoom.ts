import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";

export const ZOOM_MIN = 1;
export const ZOOM_MAX = 6;
// Feinjustierung: 0.05 pro Mausrad-Tick (vorher multiplikativ ~0.15-0.3
// bei üblichen Zoom-Stufen - zu grob für exakte Bild-zu-Bild-Deckung).
const WHEEL_STEP = 0.05;

/** Gemeinsame Pan/Zoom-Logik: Mausrad zoomt zur Cursor-Position hin, bei
 * Zoom > 1 kann per Klick+Ziehen der sichtbare Ausschnitt verschoben
 * werden (Zoom-Level bleibt dabei gleich), Doppelklick setzt beides
 * zurück. Wird von Compare (ZoomPane/OverlayPane/SliderComparePane) und
 * der Timeline-Lightbox genutzt.
 *
 * Mathematischer Ansatz: transform-origin fix auf "0 0" (Element-Ecke),
 * Transform ist `translate(tx, ty) scale(s)`. Für einen lokalen (unskal-
 * ierten) Bildpunkt p gilt dann screen = s*p + (tx,ty) - eine einfache
 * affine Abbildung, aus der sich sowohl "zoome so, dass der Punkt unter
 * dem Cursor stehen bleibt" als auch reines 1:1-Ziehen in Bildschirm-
 * Pixeln (unabhängig vom Zoom-Level) sauber herleiten lassen. scaleRef/
 * translateRef halten den aktuellen Wert für die nativen Event-Handler
 * (die nur einmal beim Mount registriert werden) immer aktuell, ohne
 * stale Closures. */
export function usePanZoom() {
  const [scale, setScale] = useState(1);
  const [translate, setTranslateState] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const scaleRef = useRef(scale);
  const translateRef = useRef(translate);
  scaleRef.current = scale;
  translateRef.current = translate;
  const containerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ startX: number; startY: number; startTx: number; startTy: number } | null>(null);

  function applyZoomAtPoint(nextScaleRaw: number, px: number, py: number) {
    const nextScale = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, nextScaleRaw));
    const s = scaleRef.current;
    const t = translateRef.current;
    const nextTranslate = {
      x: px - (nextScale / s) * (px - t.x),
      y: py - (nextScale / s) * (py - t.y),
    };
    scaleRef.current = nextScale;
    translateRef.current = nextTranslate;
    setScale(nextScale);
    setTranslateState(nextTranslate);
  }

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    // React hängt onWheel standardmäßig als PASSIVEN Listener ein - dort
    // wird preventDefault() stillschweigend ignoriert (Browser-Warnung
    // "Unable to preventDefault inside passive event listener
    // invocation"), die Seite würde beim Zoomen also trotzdem mitscrollen.
    // Deshalb hier ein nativer, explizit nicht-passiver Listener statt der
    // React-Prop.
    function handleWheel(e: WheelEvent) {
      e.preventDefault();
      const rect = el!.getBoundingClientRect();
      // Additiver statt multiplikativer Schritt: bei hohem Zoom-Level
      // wurde der alte Faktor-Ansatz (Skalierung * 1.15) spürbar grob
      // ("0.2er Sprünge") - ein fester Schritt bleibt über den gesamten
      // Zoom-Bereich gleich fein.
      const step = e.deltaY < 0 ? WHEEL_STEP : -WHEEL_STEP;
      applyZoomAtPoint(scaleRef.current + step, e.clientX - rect.left, e.clientY - rect.top);
    }

    // Klick+Ziehen verschiebt den Ausschnitt bei Zoom > 1 (reines 1:1-
    // Pixel-Dragging auf dem Bildschirm, siehe Kommentar oben).
    //
    // Eigene Drag-Handles (Schieberegler-Trennlinie, Ausrichtungsgitter-
    // Linien) liegen INNERHALB dieses Containers und müssen ihr eigenes
    // Dragging behalten, ohne gleichzeitig das Bild zu verschieben. Ein
    // e.stopPropagation() in deren React-onMouseDown reicht dafür NICHT:
    // dieser Listener hier ist ein NATIVER addEventListener direkt auf
    // dem Container-Element, das in der echten DOM-Bubble-Reihenfolge
    // VOR React's synthetischem (am React-Root delegierten) Handler
    // liegt - er feuert also bereits, bevor React's stopPropagation()
    // überhaupt ausgeführt wird. Daher hier stattdessen explizit prüfen,
    // ob das Zielelement als Drag-Handle markiert ist (data-pan-ignore).
    function handleMouseDown(e: MouseEvent) {
      if (scaleRef.current <= 1) return;
      if (e.target instanceof Element && e.target.closest("[data-pan-ignore]")) return;
      dragRef.current = {
        startX: e.clientX,
        startY: e.clientY,
        startTx: translateRef.current.x,
        startTy: translateRef.current.y,
      };
      setIsDragging(true);
    }
    function handleMouseMove(e: MouseEvent) {
      if (!dragRef.current) return;
      const nextTranslate = {
        x: dragRef.current.startTx + (e.clientX - dragRef.current.startX),
        y: dragRef.current.startTy + (e.clientY - dragRef.current.startY),
      };
      translateRef.current = nextTranslate;
      setTranslateState(nextTranslate);
    }
    function handleMouseUp() {
      dragRef.current = null;
      setIsDragging(false);
    }

    el.addEventListener("wheel", handleWheel, { passive: false });
    el.addEventListener("mousedown", handleMouseDown);
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      el.removeEventListener("wheel", handleWheel);
      el.removeEventListener("mousedown", handleMouseDown);
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function reset() {
    scaleRef.current = 1;
    translateRef.current = { x: 0, y: 0 };
    setScale(1);
    setTranslateState({ x: 0, y: 0 });
  }

  // Für den Zoom-Slider (feinstufiger als das Mausrad): zoomt um die
  // Container-Mitte, damit der Ausschnitt beim Ziehen des Reglers nicht
  // unerwartet in eine Ecke springt.
  function setScaleFromSlider(nextScale: number) {
    const el = containerRef.current;
    applyZoomAtPoint(nextScale, (el?.clientWidth ?? 0) / 2, (el?.clientHeight ?? 0) / 2);
  }

  return { scale, translate, containerRef, isDragging, reset, setScaleFromSlider };
}

export function transformStyle(translate: { x: number; y: number }, scale: number): CSSProperties {
  return { transform: `translate(${translate.x}px, ${translate.y}px) scale(${scale})`, transformOrigin: "0 0" };
}
