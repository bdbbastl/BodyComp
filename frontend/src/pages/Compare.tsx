import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import type { ReactNode } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { api, mediaUrl } from "../api/client";
import type { Photo, Pose } from "../types";
import { formatDateShortWithWeek } from "../utils/date";
import { COMPARE_ZOOM_MIN, transformStyle, usePanZoom } from "../hooks/usePanZoom";
import { ZoomSlider } from "../components/ZoomSlider";
import { BrightnessSlider, BRIGHTNESS_DEFAULT } from "../components/BrightnessSlider";
import { numberedPoseOptionLabel } from "../utils/poseLabel";
import { resolveAspectRatio } from "../utils/compareAspect";
import type { AspectPreset } from "../utils/compareAspect";
import { CompareFilterBar } from "../components/CompareFilterBar";
import { PaneAdjustments } from "../components/PaneAdjustments";
import PageHeader from "../components/PageHeader";
import { Grid3x3, ImageDown, Scan, Sparkles } from "lucide-react";
import { IconButton } from "../components/IconButton";
import { useBusyOverlay } from "../contexts/BusyOverlayContext";
import { CompareExportModal } from "../components/CompareExportModal";
import type { ExportAspect } from "../utils/compareExport";
import {
  exportFilename,
  renderSideBySideToCanvas,
  renderSliderToCanvas,
  shouldShowWatermark,
} from "../utils/compareExport";
import { useCurrentUser } from "../hooks/useCurrentUser";

type Mode = "side-by-side" | "slider";
// "all" = Sonderauswahl "Alle Posen" - zeigt alle Posen (in Settings-
// Reihenfolge) für die zwei gewählten Termine untereinander an.
type PoseSelection = number | "" | "all";
const ALL_POSES = "all";

export default function Compare() {
  const { clientId } = useParams<{ clientId: string }>();
  const clientIdNum = Number(clientId);
  const [poseSelection, setPoseSelection] = useState<PoseSelection>("");
  const { show, hide } = useBusyOverlay();
  const queryClient = useQueryClient();
  const [dateX, setDateX] = useState("");
  const [dateY, setDateY] = useState("");
  const [mode, setMode] = useState<Mode>("side-by-side");
  // Default: unverändert (Rohbilder). Checkbox aktiviert die
  // KI-Normalisierung (MediaPipe-Ausrichtung auf Körperhöhe/-neigung) für
  // beide Modi.
  const [normalize, setNormalize] = useState(false);
  // Manuelle Belichtungs-Slider statt automatischer Erkennung: die
  // automatische Messung war bei echten Fotos zu unzuverlässig (heller
  // Hintergrund verwässert den Durchschnitt) - jetzt steuert der Nutzer
  // jedes Bild einzeln, 100% = unverändert. In "Alle Posen" gilt je ein
  // gemeinsamer Regler für alle X- bzw. Y-Bilder (sonst wären es bei 20
  // Posen 40 Einzelregler).
  const [brightnessX, setBrightnessX] = useState(BRIGHTNESS_DEFAULT);
  const [brightnessY, setBrightnessY] = useState(BRIGHTNESS_DEFAULT);
  // Ausrichtungshilfe: 3 horizontale, per Klick+Ziehen verschiebbare
  // Linien (z.B. auf Brust/Hüfte/Knie legen), um zwei Fotos leichter
  // aneinander auszurichten. Ein Satz Positionen gilt für ALLE
  // gleichzeitig sichtbaren Panes (siehe AlignmentGridOverlay), damit sie
  // auf jedem Bild an derselben relativen Höhe erscheinen.
  const [showGrid, setShowGrid] = useState(false);
  const [gridLines, setGridLines] = useState<number[]>([25, 50, 75]);
  // Bleibt bewusst über Posen-/Datumswechsel hinweg bestehen (siehe
  // Design-Spec) - der User hat ihn bewusst gewählt.
  const [formatPreset, setFormatPreset] = useState<AspectPreset>("auto");
  const paneXRef = useRef<ZoomPaneHandle>(null);
  const paneYRef = useRef<ZoomPaneHandle>(null);
  const sliderPaneRef = useRef<SliderPaneHandle>(null);
  const [showExportModal, setShowExportModal] = useState(false);
  const { data: currentUser } = useCurrentUser();
  function updateGridLine(index: number, value: number) {
    setGridLines((lines) => lines.map((l, i) => (i === index ? value : l)));
  }

  const isAllPoses = poseSelection === ALL_POSES;

  const posesQuery = useQuery({
    queryKey: ["poses", clientIdNum],
    queryFn: () => api.poses.list(clientIdNum),
  });

  // Sobald eine einzelne Pose gewählt ist: alle Fotos dieser Pose laden, um
  // die Datums-Dropdowns auf die tatsächlich vorhandenen Tage zu
  // beschränken (statt einer freien Datumseingabe, bei der man leere Tage
  // treffen kann).
  const posePhotosQuery = useQuery({
    queryKey: ["photos", clientIdNum, "by-pose", poseSelection],
    queryFn: () => api.photos.list(clientIdNum, { pose_id: Number(poseSelection) }),
    enabled: typeof poseSelection === "number",
  });

  // "Alle Posen": alle zugeordneten Fotos laden (posenübergreifend), um
  // sowohl die Datums-Dropdowns zu befüllen als auch pro Pose das Bildpaar
  // für die zwei gewählten Termine client-seitig herauszusuchen.
  const allPhotosQuery = useQuery({
    queryKey: ["photos", clientIdNum, "all-for-compare"],
    queryFn: () => api.photos.list(clientIdNum),
    select: (photos) => photos.filter((p) => p.pose_id != null),
    enabled: isAllPoses,
  });

  const availableDates = [
    ...new Set(
      (isAllPoses ? allPhotosQuery.data ?? [] : posePhotosQuery.data ?? []).map((p) =>
        p.taken_at.slice(0, 10)
      )
    ),
  ].sort((a, b) => (a < b ? 1 : -1)); // absteigend, neueste zuerst

  const comparisonQuery = useQuery({
    queryKey: ["comparison", clientIdNum, poseSelection, dateX, dateY],
    queryFn: () =>
      api.comparisons.get(clientIdNum, { pose_id: Number(poseSelection), date_x: dateX, date_y: dateY }),
    enabled: typeof poseSelection === "number" && dateX !== "" && dateY !== "",
    placeholderData: keepPreviousData,
    retry: false,
  });

  const poses = posesQuery.data ?? [];
  const result = comparisonQuery.data;
  const aspectRatio = resolveAspectRatio(formatPreset, result?.photo_x, result?.photo_y);

  // Für "Alle Posen": pro Pose (Settings-Reihenfolge) das Bildpaar der
  // zwei gewählten Termine heraussuchen - Posen ohne beide Fotos werden
  // übersprungen, statt Lücken anzuzeigen.
  const allPosePairs =
    isAllPoses && dateX !== "" && dateY !== ""
      ? poses
          .map((pose) => {
            const photos = allPhotosQuery.data ?? [];
            const photoX = photos.find(
              (p) => p.pose_id === pose.id && p.taken_at.slice(0, 10) === dateX
            );
            const photoY = photos.find(
              (p) => p.pose_id === pose.id && p.taken_at.slice(0, 10) === dateY
            );
            return { pose, photoX, photoY };
          })
          .filter((entry): entry is { pose: Pose; photoX: Photo; photoY: Photo } =>
            Boolean(entry.photoX && entry.photoY)
          )
      : [];

  // Neues Foto-Paar geladen -> Helligkeitsregler auf Standard zurücksetzen,
  // damit die Einstellung des vorherigen Paars nicht fälschlich übernommen
  // wird.
  useEffect(() => {
    setBrightnessX(BRIGHTNESS_DEFAULT);
    setBrightnessY(BRIGHTNESS_DEFAULT);
  }, [result?.photo_x.id, result?.photo_y.id]);

  // Pose per Pfeil-Buttons/Tastatur durchblättern (wrap-around am Anfang/
  // Ende). Datum X/Y bleiben dabei bewusst unverändert - nur die Pose
  // wechselt. In "Alle Posen" ergibt Pfeil-Navigation keinen Sinn (es gibt
  // keine "nächste" Pose mehr) - dort no-op.
  function goToPose(delta: number) {
    if (poses.length === 0 || isAllPoses) return;
    const currentIndex = poses.findIndex((p) => p.id === poseSelection);
    const baseIndex = currentIndex === -1 ? (delta > 0 ? -1 : 0) : currentIndex;
    const nextIndex = (baseIndex + delta + poses.length) % poses.length;
    setPoseSelection(poses[nextIndex].id);
  }

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const tag = (document.activeElement?.tagName ?? "").toLowerCase();
      // Pfeiltasten in Formularfeldern (z.B. <select>) nicht kapern -
      // dort haben sie ihre eigene, erwartete Funktion.
      if (["input", "select", "textarea"].includes(tag)) return;
      if (e.key === "ArrowLeft") goToPose(-1);
      if (e.key === "ArrowRight") goToPose(1);
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [poseSelection, poses]);

  // Nachbar-Posen im Hintergrund vorladen (Vergleichsdaten + Bilddateien),
  // damit ein Klick auf ‹/› meist schon auf warme Daten trifft, statt
  // jedes Mal neu zu laden - siehe Live-Feedback "ruckelfreies Wechseln".
  // Nur bei einer einzelnen gewählten Pose (nicht "Alle Posen", wo es
  // keine Nachbar-Navigation gibt) und nur wenn beide Termine gewählt sind.
  useEffect(() => {
    if (typeof poseSelection !== "number" || dateX === "" || dateY === "" || poses.length < 2) {
      return;
    }
    const currentIndex = poses.findIndex((p) => p.id === poseSelection);
    if (currentIndex === -1) return;
    const prevPose = poses[(currentIndex - 1 + poses.length) % poses.length];
    const nextPose = poses[(currentIndex + 1) % poses.length];

    [prevPose, nextPose].forEach((neighborPose) => {
      queryClient
        .prefetchQuery({
          queryKey: ["comparison", clientIdNum, neighborPose.id, dateX, dateY],
          queryFn: () =>
            api.comparisons.get(clientIdNum, {
              pose_id: neighborPose.id,
              date_x: dateX,
              date_y: dateY,
            }),
        })
        .then(() => {
          const cached = queryClient.getQueryData<{
            photo_x: Photo;
            photo_y: Photo;
          }>(["comparison", clientIdNum, neighborPose.id, dateX, dateY]);
          if (!cached) return;
          // Bild-Bytes selbst vorwärmen (Browser-HTTP-Cache + serverseitiger
          // ensure_local()-Cache über den normalen /media-Request) - die
          // Vergleichsdaten allein enthalten nur Pfade, keine Bilddaten.
          [cached.photo_x, cached.photo_y].forEach((photo) => {
            const src = mediaUrl(
              normalize && photo.normalized_path ? photo.normalized_path : photo.display_path
            );
            new Image().src = src;
          });
        })
        .catch(() => {
          // Best effort - ein fehlgeschlagenes Prefetch (z.B. Nachbar-Pose
          // hat für dieses Datumspaar kein Foto) soll nichts sichtbar
          // beeinträchtigen, das eigentliche Umschalten zeigt den Fehler
          // ggf. ganz normal über comparisonQuery.isError an.
        });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [poseSelection, dateX, dateY, poses, clientIdNum, normalize]);

  // KI-Judge-Analyse: läuft ausschließlich per Knopfdruck (siehe Button
  // unten), nie automatisch beim Auswählen von Pose/Datum - jeder Aufruf
  // kostet echte API-Anfragen. Zwei getrennte Mutations, je nachdem ob
  // eine Einzelpose oder "Alle Posen" gewählt ist.
  const aiAnalysisMutation = useMutation({
    mutationFn: () =>
      api.comparisons.aiAnalysis(clientIdNum, {
        pose_id: Number(poseSelection),
        date_x: dateX,
        date_y: dateY,
      }),
    onSuccess: () => hide(),
    onError: () => hide(),
  });
  const aiAnalysisAllMutation = useMutation({
    mutationFn: () => api.comparisons.aiAnalysisAll(clientIdNum, { date_x: dateX, date_y: dateY }),
    onSuccess: () => hide(),
    onError: () => hide(),
  });
  const activeAiMutation = isAllPoses ? aiAnalysisAllMutation : aiAnalysisMutation;

  // Elapsed-Time-Indikator während der Gemini-Anfrage: es gibt kein
  // Backend-Streaming, das den Fortschritt melden könnte, also einfach
  // clientseitig hochzählen - zeigt dem User zumindest, dass der Request
  // noch lebt und wie lange er schon läuft (Anfragen dauern erfahrungsgemäß
  // mehrere Sekunden bis über eine Minute, v.a. bei Serverüberlastung mit
  // automatischen Retries im Backend, oder länger bei "Alle Posen" mit
  // bis zu 40 Bildern in einer Anfrage).
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  useEffect(() => {
    if (!activeAiMutation.isPending) {
      setElapsedSeconds(0);
      return;
    }
    const start = Date.now();
    const interval = setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - start) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [activeAiMutation.isPending]);

  // Neue Pose/Datum gewählt -> alten Analyse-Text verwerfen, damit er nicht
  // fälschlich als Bewertung des neuen Foto-Paars missverstanden wird.
  useEffect(() => {
    aiAnalysisMutation.reset();
    aiAnalysisAllMutation.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [poseSelection, dateX, dateY]);

  const missingNormalized =
    normalize &&
    !!result &&
    (!result.photo_x.normalized_path || !result.photo_y.normalized_path);

  // Früher steuerte diese Bedingung, OB der KI-Button überhaupt gerendert
  // wird. Im Header bleibt der Button dauerhaft sichtbar und wird
  // stattdessen deaktiviert - sonst würde die Icon-Reihe je nach Auswahl
  // ihre Breite ändern.
  const canAnalyze = (isAllPoses && allPosePairs.length > 0) || (!isAllPoses && !!result);

  const resolveSrc = (photo: Photo) =>
    mediaUrl(normalize && photo.normalized_path ? photo.normalized_path : photo.display_path);

  const filterFor = (brightness: number) =>
    brightness === BRIGHTNESS_DEFAULT ? undefined : `brightness(${brightness}%)`;

  // Gemeinsamer Render-Pfad für Export UND Big Mode - beide sollen
  // exakt dieselbe Geometrie zeigen (siehe Design-Spec Leitprinzip).
  // Unterscheiden sich nur in der Zielgröße (fest vs. bildschirmfüllend)
  // und im Wasserzeichen (nur beim echten Download).
  const renderComparisonToCanvas = useCallback(
    (
      canvas: HTMLCanvasElement,
      target: ExportAspect | { width: number; height: number },
      showWatermark: boolean
    ) => {
      if (!result) return;
      const imgX = new Image();
      const imgY = new Image();
      imgX.crossOrigin = "anonymous";
      imgY.crossOrigin = "anonymous";
      imgX.src = resolveSrc(result.photo_x);
      imgY.src = resolveSrc(result.photo_y);
      const draw = () => {
        if (!imgX.complete || !imgY.complete) return;
        if (mode === "side-by-side") {
          const stateX = paneXRef.current?.getExportState();
          const stateY = paneYRef.current?.getExportState();
          if (!stateX || !stateY) return;
          renderSideBySideToCanvas(
            canvas,
            target,
            imgX,
            { ...stateX, brightness: brightnessX },
            imgY,
            { ...stateY, brightness: brightnessY },
            showWatermark
          );
        } else {
          const sliderState = sliderPaneRef.current?.getExportState();
          if (!sliderState) return;
          renderSliderToCanvas(
            canvas,
            target,
            imgX,
            imgY,
            {
              ...sliderState,
              x: { ...sliderState.x, brightness: brightnessX },
              y: { ...sliderState.y, brightness: brightnessY },
            },
            showWatermark
          );
        }
      };
      imgX.onload = draw;
      imgY.onload = draw;
      draw();
    },
    [result, mode, brightnessX, brightnessY]
  );

  const handleExportRender = useCallback(
    (canvas: HTMLCanvasElement, aspect: ExportAspect) => {
      renderComparisonToCanvas(canvas, aspect, shouldShowWatermark(currentUser));
    },
    [renderComparisonToCanvas, currentUser]
  );

  const handleBigModeRender = useCallback(
    (canvas: HTMLCanvasElement, dims: { width: number; height: number }) => {
      renderComparisonToCanvas(canvas, dims, false);
    },
    [renderComparisonToCanvas]
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Compare"
        actions={
          <>
            <IconButton
              icon={Scan}
              label="KI-Normalisierung (Ausrichtung & Skalierung)"
              toggle
              active={normalize}
              onClick={() => setNormalize((v) => !v)}
            />
            <IconButton
              icon={Grid3x3}
              label="Ausrichtungsgitter"
              toggle
              active={showGrid}
              onClick={() => setShowGrid((v) => !v)}
            />
            <span className="mx-1 h-6 w-px bg-white/10" aria-hidden="true" />
            <IconButton
              icon={Sparkles}
              label={
                isAllPoses
                  ? `KI-Gesamtanalyse (${allPosePairs.length} Posen)`
                  : "KI-Analyse (Judge-Bewertung)"
              }
              variant="accent"
              pending={activeAiMutation.isPending}
              disabled={!canAnalyze}
              badge={isAllPoses && allPosePairs.length > 0 ? allPosePairs.length : undefined}
              onClick={() => {
                show("Judge analyzing…");
                activeAiMutation.mutate();
              }}
            />
            {!isAllPoses && (
              <IconButton
                icon={ImageDown}
                label="Vergleich exportieren"
                disabled={!result}
                onClick={() => setShowExportModal(true)}
              />
            )}
          </>
        }
      />

      <CompareFilterBar
        poses={poses}
        poseValue={poseSelection === "" ? "" : String(poseSelection)}
        onPoseChange={(value) =>
          setPoseSelection(value === "" ? "" : value === ALL_POSES ? ALL_POSES : Number(value))
        }
        onNavigate={goToPose}
        navigationDisabled={isAllPoses || poses.length === 0}
        allPosesValue={ALL_POSES}
        dateX={dateX}
        dateY={dateY}
        onDateXChange={setDateX}
        onDateYChange={setDateY}
        availableDates={availableDates}
        datesDisabled={poseSelection === "" || availableDates.length === 0}
        datePlaceholder={poseSelection === "" ? "Choose pose first…" : "Choose date…"}
        formatDate={formatDate}
        mode={mode}
        onModeChange={setMode}
        showModeSwitch={!isAllPoses}
        formatPreset={formatPreset}
        onFormatPresetChange={setFormatPreset}
      />

      {!isAllPoses && comparisonQuery.isError && (
        <p className="text-red-400">
          At least one of the dates has no photo for this pose.
        </p>
      )}

      {poseSelection !== "" && availableDates.length === 0 && !posePhotosQuery.isLoading && !allPhotosQuery.isLoading && (
        <p className="text-slate-500">
          {isAllPoses ? "No assigned photos yet." : "No photos assigned to this pose yet."}
        </p>
      )}

      {isAllPoses && dateX !== "" && dateY !== "" && allPosePairs.length === 0 && (
        <p className="text-slate-500">No pose has photos on both selected dates.</p>
      )}

      {!isAllPoses && missingNormalized && (
        <p className="rounded-lg bg-yellow-500/10 px-3 py-2 text-sm text-yellow-400">
          At least one of the images has no normalized version available
          (normalization failed or is pending) — the original image is shown instead.
        </p>
      )}

      {activeAiMutation.isPending && (
        <p className="flex items-center justify-center gap-2 text-xs text-accent">
          <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-accent" />
          Judge analysiert… {elapsedSeconds}s
          {elapsedSeconds > 20 && " (Gemini wiederholt automatisch bei Serverlast)"}
        </p>
      )}

      {activeAiMutation.isError && (
        <p className="rounded-lg bg-red-500/10 px-3 py-2 text-sm text-red-400">
          {(activeAiMutation.error as { response?: { data?: { detail?: string } } })?.response
            ?.data?.detail ?? "AI analysis failed."}
        </p>
      )}

      {activeAiMutation.data && <JudgeAnalysis text={activeAiMutation.data.analysis} />}

      {!isAllPoses && result && mode === "side-by-side" && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <ComparePane
            ref={paneXRef}
            label={formatDate(dateX)}
            src={resolveSrc(result.photo_x)}
            filter={filterFor(brightnessX)}
            brightness={brightnessX}
            onBrightnessChange={setBrightnessX}
            aspectRatio={aspectRatio}
            showGrid={showGrid}
            gridLines={gridLines}
            onGridLineChange={updateGridLine}
          />
          <ComparePane
            ref={paneYRef}
            label={formatDate(dateY)}
            src={resolveSrc(result.photo_y)}
            filter={filterFor(brightnessY)}
            brightness={brightnessY}
            onBrightnessChange={setBrightnessY}
            aspectRatio={aspectRatio}
            showGrid={showGrid}
            gridLines={gridLines}
            onGridLineChange={updateGridLine}
          />
        </div>
      )}

      {!isAllPoses && result && mode === "slider" && (
        <div className="space-y-4">
          {!normalize && (
            <p className="rounded-lg bg-yellow-500/10 px-3 py-2 text-sm text-yellow-400">
              Without AI normalization, camera distance/tilt usually won't match between the
              photos — enable the checkbox above for a clean slider comparison.
            </p>
          )}
          <SliderComparePane
            ref={sliderPaneRef}
            key={`${result.photo_x.id}-${result.photo_y.id}`}
            srcX={resolveSrc(result.photo_x)}
            srcY={resolveSrc(result.photo_y)}
            filterX={filterFor(brightnessX)}
            filterY={filterFor(brightnessY)}
            brightnessX={brightnessX}
            onBrightnessXChange={setBrightnessX}
            brightnessY={brightnessY}
            onBrightnessYChange={setBrightnessY}
            altX={formatDate(dateX)}
            altY={formatDate(dateY)}
            aspectRatio={aspectRatio}
            showGrid={showGrid}
            gridLines={gridLines}
            onGridLineChange={updateGridLine}
          />
        </div>
      )}

      {isAllPoses && allPosePairs.length > 0 && (
        <div className="space-y-8">
          <div className="mx-auto grid max-w-md grid-cols-1 gap-x-6 gap-y-4 rounded-xl border border-white/5 bg-surface p-4 sm:grid-cols-2">
            <BrightnessSlider value={brightnessX} onChange={setBrightnessX} />
            <BrightnessSlider value={brightnessY} onChange={setBrightnessY} />
          </div>
          {allPosePairs.map(({ pose, photoX, photoY }) => {
            // Jede Pose hat ihr eigenes Fotopaar und damit potenziell
            // ihre eigene Auto-Form - der formatPreset selbst ist ein
            // einziger globaler Wert, nur das Auto-Ergebnis ist pro Zeile
            // unterschiedlich (siehe Design-Spec Abschnitt 3).
            const rowAspectRatio = resolveAspectRatio(formatPreset, photoX, photoY);
            return (
              <section key={pose.id} className="space-y-2">
                <h2 className="text-base font-semibold text-white">
                  {numberedPoseOptionLabel(poses.findIndex((p) => p.id === pose.id), pose.name)}
                </h2>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <ComparePane
                    label={formatDate(dateX)}
                    src={resolveSrc(photoX)}
                    filter={filterFor(brightnessX)}
                    brightness={brightnessX}
                    onBrightnessChange={setBrightnessX}
                    aspectRatio={rowAspectRatio}
                    showBrightnessSlider={false}
                    showGrid={showGrid}
                    gridLines={gridLines}
                    onGridLineChange={updateGridLine}
                  />
                  <ComparePane
                    label={formatDate(dateY)}
                    src={resolveSrc(photoY)}
                    filter={filterFor(brightnessY)}
                    brightness={brightnessY}
                    onBrightnessChange={setBrightnessY}
                    aspectRatio={rowAspectRatio}
                    showBrightnessSlider={false}
                    showGrid={showGrid}
                    gridLines={gridLines}
                    onGridLineChange={updateGridLine}
                  />
                </div>
              </section>
            );
          })}
        </div>
      )}

      {showExportModal && result && (
        <CompareExportModal
          onClose={() => setShowExportModal(false)}
          filename={exportFilename(`client-${clientIdNum}`, dateX, dateY)}
          render={handleExportRender}
        />
      )}
    </div>
  );
}

function formatDate(iso: string): string {
  return formatDateShortWithWeek(iso);
}

/** Zerlegt Inline-Markdown (aktuell nur **fett**) in React-Knoten, damit
 * von Gemini zurückgegebene Hervorhebungen (siehe Screenshot-Feedback) im
 * Frontend auch tatsächlich fett dargestellt werden statt die "**"
 * wörtlich anzuzeigen. */
function renderInlineMarkdown(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return (
        <strong key={i} className="font-semibold text-white">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

/**
 * Rendert die KI-Antwort (Markdown mit "## Überschrift" + "- Bullet"
 * Struktur, siehe backend/app/services/ai_comparison.py JUDGE_PROMPT).
 * Inline-Fettschrift ("**...**") wird über renderInlineMarkdown in <strong>
 * umgewandelt. Bewusst ohne vollständige Markdown-Library - das Format ist
 * konstant genug für ein paar Zeilen Parsing.
 */
function JudgeAnalysis({ text }: { text: string }) {
  const lines = text.split("\n");
  const blocks: { heading: string | null; items: string[] }[] = [];
  let current: { heading: string | null; items: string[] } = { heading: null, items: [] };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) continue;
    if (line.startsWith("## ")) {
      if (current.heading || current.items.length) blocks.push(current);
      current = { heading: line.slice(3).trim(), items: [] };
    } else if (line.startsWith("- ") || line.startsWith("* ")) {
      current.items.push(line.slice(2).trim());
    } else {
      current.items.push(line);
    }
  }
  if (current.heading || current.items.length) blocks.push(current);

  return (
    <div className="space-y-5 rounded-xl border border-white/5 bg-surface p-5">
      {blocks.map((block, i) => (
        <div key={i} className="space-y-2">
          {block.heading && (
            <h3 className="text-base font-semibold text-accent">
              {renderInlineMarkdown(block.heading)}
            </h3>
          )}
          <ul className="list-disc space-y-1.5 pl-5 text-sm text-slate-300">
            {block.items.map((item, j) => (
              <li key={j}>{renderInlineMarkdown(item)}</li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

/**
 * Ausrichtungshilfe: 3 horizontale Linien, die per Klick+Ziehen vertikal
 * verschoben werden können (z.B. eine auf Brust-, eine auf Hüft-, eine
 * auf Knie-Höhe legen), um zwei Fotos leichter aneinander auszurichten.
 * `lines` wird vom übergeordneten Compare-State verwaltet und an ALLE
 * gleichzeitig sichtbaren Panes weitergereicht, damit dieselben Linien
 * (gleicher %-Wert) auf jedem Bild an derselben relativen Höhe erscheinen
 * - nur so lässt sich vergleichen, ob z.B. die Brust auf beiden Fotos auf
 * gleicher Höhe sitzt. data-pan-ignore verhindert, dass das Ziehen einer
 * Linie stattdessen das Bild verschiebt (siehe usePanZoom-Kommentar).
 */
function AlignmentGridOverlay({
  lines,
  onChange,
}: {
  lines: number[];
  onChange: (index: number, value: number) => void;
}) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const draggingIndexRef = useRef<number | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    function handleMove(e: MouseEvent) {
      const index = draggingIndexRef.current;
      if (index === null || !overlayRef.current) return;
      const rect = overlayRef.current.getBoundingClientRect();
      const pct = ((e.clientY - rect.top) / rect.height) * 100;
      onChangeRef.current(index, Math.min(100, Math.max(0, pct)));
    }
    function handleUp() {
      draggingIndexRef.current = null;
    }
    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleUp);
    return () => {
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleUp);
    };
  }, []);

  return (
    <div ref={overlayRef} className="pointer-events-none absolute inset-0 z-30">
      {lines.map((pct, index) => (
        <div
          key={index}
          data-pan-ignore
          className="pointer-events-auto absolute inset-x-0 -translate-y-1/2 cursor-row-resize py-2"
          style={{ top: `${pct}%` }}
          onMouseDown={(e) => {
            e.stopPropagation();
            draggingIndexRef.current = index;
          }}
        >
          <div className="h-0.5 w-full bg-cyan-400 shadow-[0_0_4px_rgba(34,211,238,0.9)]" />
        </div>
      ))}
    </div>
  );
}

/** Einzelbild mit Mausrad-Zoom + Klick-Ziehen (zoomt zur Cursor-Position,
 * Doppelklick setzt zurück), plus Zoom- und Neigungs-Slider für die
 * Feinjustierung. key={src} an der Aufrufstelle sorgt dafür, dass
 * Zoom/Pan/Neigung bei einem neuen Foto automatisch zurückgesetzt werden.
 * Die Rotation wird auf einer inneren Ebene angewendet (eigenes
 * transform-origin "Bildmitte"), damit sie unabhängig von der Pan/Zoom-
 * Mathematik der äußeren Ebene (transform-origin "0 0") bleibt. */
/**
 * Bild + zugehöriges Kontroll-Panel als EINE zusammenhängende Einheit
 * (Bildunterschrift, Zoom, Rotation, optional Belichtung) - bewusst als
 * ein durchgehender, gleichmäßig eingerückter Block statt verstreuter
 * Einzel-Regler, damit die Zuordnung "welcher Regler gehört zu welchem
 * Bild" auf einen Blick klar ist.
 */
export interface ZoomPaneHandle {
  getExportState: () => {
    scale: number;
    translateX: number;
    translateY: number;
    rotation: number;
    containerWidth: number;
    containerHeight: number;
  };
}

const ZoomPane = forwardRef<ZoomPaneHandle, {
  src: string;
  alt: string;
  filter: string | undefined;
  caption?: ReactNode;
  brightness?: number;
  onBrightnessChange?: (value: number) => void;
  showBrightnessSlider?: boolean;
  showGrid?: boolean;
  gridLines?: number[];
  onGridLineChange?: (index: number, value: number) => void;
  aspectRatio?: number;
}>(function ZoomPane(
  {
    src,
    alt,
    filter,
    caption,
    brightness,
    onBrightnessChange,
    showBrightnessSlider = true,
    showGrid,
    gridLines,
    onGridLineChange,
    aspectRatio = 3 / 4,
  },
  ref
) {
  const { scale, translate, containerRef, isDragging, reset, setScaleFromSlider } = usePanZoom({
    zoomMin: COMPARE_ZOOM_MIN,
  });
  const [rotation, setRotation] = useState(0);

  useImperativeHandle(ref, () => ({
    // Container-Pixelgröße wird live mitgeliefert, damit der Export
    // translateX/Y (in Live-CSS-Pixeln) korrekt in die - meist deutlich
    // größere - Export-Canvas-Auflösung umrechnen kann (siehe
    // compareExport.ts drawPhotoIntoRegion). Fallback 1x1 nur zur
    // Division-durch-0-Vermeidung, falls containerRef noch nicht
    // gemountet ist.
    getExportState: () => {
      const rect = containerRef.current?.getBoundingClientRect();
      return {
        scale,
        translateX: translate.x,
        translateY: translate.y,
        rotation,
        containerWidth: rect?.width || 1,
        containerHeight: rect?.height || 1,
      };
    },
  }));

  return (
    <div>
      <div
        ref={containerRef}
        className="relative w-full overflow-hidden bg-background"
        style={{ aspectRatio, cursor: scale > 1 ? (isDragging ? "grabbing" : "grab") : "zoom-in" }}
        onDoubleClick={reset}
        title="Scroll to zoom, click+drag to pan while zoomed, double-click to reset"
      >
        <div className="h-full w-full" style={transformStyle(translate, scale)}>
          <img
            src={src}
            alt={alt}
            draggable={false}
            className="h-full w-full object-cover"
            style={{ filter, transform: `rotate(${rotation}deg)` }}
          />
        </div>
        {showGrid && gridLines && onGridLineChange && (
          <AlignmentGridOverlay lines={gridLines} onChange={onGridLineChange} />
        )}
        {scale !== 1 && (
          <span className="pointer-events-none absolute bottom-1 right-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-slate-200">
            {scale.toFixed(2)}×
          </span>
        )}
      </div>
      <div>
        {caption && <p className="px-3.5 pt-3 text-sm font-medium text-slate-300">{caption}</p>}
        <PaneAdjustments
          scale={scale}
          onScaleChange={setScaleFromSlider}
          rotation={rotation}
          onRotationChange={setRotation}
          brightness={showBrightnessSlider ? brightness : undefined}
          onBrightnessChange={showBrightnessSlider ? onBrightnessChange : undefined}
          zoomMin={COMPARE_ZOOM_MIN}
          onReset={() => {
            reset();
            setRotation(0);
            if (showBrightnessSlider && onBrightnessChange) onBrightnessChange(BRIGHTNESS_DEFAULT);
          }}
        />
      </div>
    </div>
  );
});

/** Schieberegler-Vergleich: eine vertikale Trennlinie, die man horizontal
 * hin- und herziehen kann - links Bild X, rechts Bild Y (klassischer
 * Vorher/Nachher-Slider). Besonders bei geraden Posen (z.B. Front
 * Relaxed) hilfreich, um exakt dieselbe Körperstelle direkt nebeneinander
 * zu sehen. Zoom/Pan wirken auf beide Bilder gleich (siehe usePanZoom),
 * damit sie beim Zoomen deckungsgleich bleiben; ein zusätzlicher
 * Zoom-Slider erlaubt feinstufiges Nachjustieren über das Mausrad hinaus. */
export interface SliderPaneHandle {
  getExportState: () => {
    scale: number;
    translateX: number;
    translateY: number;
    dividerPct: number;
    containerWidth: number;
    containerHeight: number;
    x: { offsetX: number; offsetY: number; fineZoom: number; rotation: number };
    y: { offsetX: number; offsetY: number; fineZoom: number; rotation: number };
  };
}

const SliderComparePane = forwardRef<SliderPaneHandle, {
  srcX: string;
  srcY: string;
  filterX: string | undefined;
  filterY: string | undefined;
  brightnessX: number;
  onBrightnessXChange: (value: number) => void;
  brightnessY: number;
  onBrightnessYChange: (value: number) => void;
  altX: string;
  altY: string;
  showGrid?: boolean;
  gridLines?: number[];
  onGridLineChange?: (index: number, value: number) => void;
  aspectRatio?: number;
}>(function SliderComparePane(
  {
    srcX,
    srcY,
    filterX,
    filterY,
    brightnessX,
    onBrightnessXChange,
    brightnessY,
    onBrightnessYChange,
    altX,
    altY,
    showGrid,
    gridLines,
    onGridLineChange,
    aspectRatio = 3 / 4,
  },
  ref
) {
  const { scale, translate, containerRef, isDragging, reset, setScaleFromSlider } = usePanZoom({
    zoomMin: COMPARE_ZOOM_MIN,
  });
  const [dividerPct, setDividerPct] = useState(50);
  const [rotationX, setRotationX] = useState(0);
  const [rotationY, setRotationY] = useState(0);
  // Zusätzlich zum gemeinsamen Pan/Zoom (zum groben gemeinsamen Navigieren
  // per Mausrad/Ziehen) noch ein unabhängiger Fein-Zoom pro Bild - z.B.
  // wenn der Kameraabstand zwischen den beiden Aufnahmen unterschiedlich
  // war und ein Bild dadurch grundsätzlich kleiner/größer wirkt.
  const [fineZoomX, setFineZoomX] = useState(1);
  const [fineZoomY, setFineZoomY] = useState(1);
  // Ebenso ein unabhängiger Positions-Feinabgleich pro Bild (in px,
  // horizontal/vertikal) - das gemeinsame Klick+Ziehen verschiebt immer
  // BEIDE Bilder gleich, taugt also nur zum groben gemeinsamen
  // Navigieren. Für "linkes Bild sitzt etwas höher als rechtes, will nur
  // das linke ein paar Pixel runterschieben" braucht es einen Versatz pro
  // Bild statt eines gemeinsamen.
  const [offsetX, setOffsetX] = useState({ x: 0, y: 0 });
  const [offsetY, setOffsetY] = useState({ x: 0, y: 0 });
  const draggingDividerRef = useRef(false);

  useImperativeHandle(ref, () => ({
    getExportState: () => {
      const rect = containerRef.current?.getBoundingClientRect();
      return {
        scale,
        translateX: translate.x,
        translateY: translate.y,
        dividerPct,
        containerWidth: rect?.width || 1,
        containerHeight: rect?.height || 1,
        x: { offsetX: offsetX.x, offsetY: offsetX.y, fineZoom: fineZoomX, rotation: rotationX },
        y: { offsetX: offsetY.x, offsetY: offsetY.y, fineZoom: fineZoomY, rotation: rotationY },
      };
    },
  }));

  useEffect(() => {
    function handleMove(e: MouseEvent) {
      if (!draggingDividerRef.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const pct = ((e.clientX - rect.left) / rect.width) * 100;
      setDividerPct(Math.min(100, Math.max(0, pct)));
    }
    function handleUp() {
      draggingDividerRef.current = false;
    }
    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleUp);
    return () => {
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleUp);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-3">
      <div
        ref={containerRef}
        className="relative mx-auto max-w-md overflow-hidden rounded-xl border border-white/5 bg-background select-none"
        style={{ aspectRatio, cursor: scale > 1 ? (isDragging ? "grabbing" : "grab") : "default" }}
        onDoubleClick={reset}
        title="Scroll to zoom, click+drag to pan while zoomed, drag the divider to compare"
      >
        {/* Bild Y als volle Basis-Ebene */}
        <div className="absolute inset-0" style={transformStyle(translate, scale)}>
          <img
            src={srcY}
            alt={altY}
            draggable={false}
            className="h-full w-full object-cover"
            style={{
              filter: filterY,
              transform: `translate(${offsetY.x}px, ${offsetY.y}px) scale(${fineZoomY}) rotate(${rotationY}deg)`,
            }}
          />
        </div>
        {/* Bild X darüber, per clip-path auf den linken Divider-Anteil begrenzt */}
        <div
          className="absolute inset-0 overflow-hidden"
          style={{ clipPath: `inset(0 ${100 - dividerPct}% 0 0)` }}
        >
          <div className="absolute inset-0" style={transformStyle(translate, scale)}>
            <img
              src={srcX}
              alt={altX}
              draggable={false}
              className="h-full w-full object-cover"
              style={{
                filter: filterX,
                transform: `translate(${offsetX.x}px, ${offsetX.y}px) scale(${fineZoomX}) rotate(${rotationX}deg)`,
              }}
            />
          </div>
        </div>
        {showGrid && gridLines && onGridLineChange && (
          <AlignmentGridOverlay lines={gridLines} onChange={onGridLineChange} />
        )}
        {/* Trennlinie + Griff */}
        <div
          data-pan-ignore
          className="absolute inset-y-0 z-40 w-0.5 cursor-ew-resize bg-white/90"
          style={{ left: `${dividerPct}%` }}
          onMouseDown={(e) => {
            e.stopPropagation();
            draggingDividerRef.current = true;
          }}
        >
          <div className="absolute left-1/2 top-1/2 flex h-8 w-8 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-white text-sm text-slate-900 shadow">
            ⇔
          </div>
        </div>
        {scale !== 1 && (
          <span className="pointer-events-none absolute bottom-1 right-1 z-10 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-slate-200">
            {scale.toFixed(1)}×
          </span>
        )}
        <span className="pointer-events-none absolute bottom-1 left-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-slate-200">
          {altX}
        </span>
        <span className="pointer-events-none absolute right-1 top-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-slate-200">
          {altY}
        </span>
      </div>
      <div className="mx-auto max-w-2xl space-y-4 rounded-xl border border-white/5 bg-surface p-4">
        <ZoomSlider label="Zoom (shared)" scale={scale} onChange={setScaleFromSlider} />
        <div className="grid grid-cols-1 gap-x-8 border-t border-white/5 pt-3 sm:grid-cols-2">
          <div>
            <p className="px-3 text-sm font-medium text-slate-300">{altX}</p>
            <PaneAdjustments
              scale={fineZoomX}
              onScaleChange={setFineZoomX}
              rotation={rotationX}
              onRotationChange={setRotationX}
              offset={offsetX}
              onOffsetChange={setOffsetX}
              brightness={brightnessX}
              onBrightnessChange={onBrightnessXChange}
              zoomMin={COMPARE_ZOOM_MIN}
              onReset={() => {
                setFineZoomX(1);
                setRotationX(0);
                setOffsetX({ x: 0, y: 0 });
                onBrightnessXChange(BRIGHTNESS_DEFAULT);
              }}
            />
          </div>
          <div>
            <p className="px-3 text-sm font-medium text-slate-300">{altY}</p>
            <PaneAdjustments
              scale={fineZoomY}
              onScaleChange={setFineZoomY}
              rotation={rotationY}
              onRotationChange={setRotationY}
              offset={offsetY}
              onOffsetChange={setOffsetY}
              brightness={brightnessY}
              onBrightnessChange={onBrightnessYChange}
              zoomMin={COMPARE_ZOOM_MIN}
              onReset={() => {
                setFineZoomY(1);
                setRotationY(0);
                setOffsetY({ x: 0, y: 0 });
                onBrightnessYChange(BRIGHTNESS_DEFAULT);
              }}
            />
          </div>
        </div>
      </div>
    </div>
  );
});

const ComparePane = forwardRef<ZoomPaneHandle, {
  label: string;
  src: string;
  filter: string | undefined;
  brightness: number;
  onBrightnessChange: (value: number) => void;
  aspectRatio?: number;
  showBrightnessSlider?: boolean;
  showGrid?: boolean;
  gridLines?: number[];
  onGridLineChange?: (index: number, value: number) => void;
}>(function ComparePane(
  {
    label,
    src,
    filter,
    brightness,
    onBrightnessChange,
    aspectRatio = 3 / 4,
    showBrightnessSlider = true,
    showGrid,
    gridLines,
    onGridLineChange,
  },
  ref
) {
  return (
    <figure className="overflow-hidden rounded-xl border border-white/5 bg-surface">
      <ZoomPane
        ref={ref}
        key={src}
        src={src}
        alt={label}
        filter={filter}
        caption={label}
        brightness={brightness}
        onBrightnessChange={onBrightnessChange}
        aspectRatio={aspectRatio}
        showBrightnessSlider={showBrightnessSlider}
        showGrid={showGrid}
        gridLines={gridLines}
        onGridLineChange={onGridLineChange}
      />
    </figure>
  );
});
