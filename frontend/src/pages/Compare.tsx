import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, mediaUrl } from "../api/client";
import type { Photo, Pose } from "../types";
import { formatDateShortWithWeek } from "../utils/date";
import { transformStyle, usePanZoom } from "../hooks/usePanZoom";
import { ZoomSlider } from "../components/ZoomSlider";
import { RotationSlider } from "../components/RotationSlider";
import { PositionSlider } from "../components/PositionSlider";
import { SliderControl } from "../components/SliderControl";
import { numberedPoseOptionLabel } from "../utils/poseLabel";

type Mode = "side-by-side" | "overlay" | "slider";
// "all" = Sonderauswahl "Alle Posen" - zeigt alle Posen (in Settings-
// Reihenfolge) für die zwei gewählten Termine untereinander an.
type PoseSelection = number | "" | "all";
const ALL_POSES = "all";

const BRIGHTNESS_MIN = 50;
const BRIGHTNESS_MAX = 250;
const BRIGHTNESS_DEFAULT = 100;

export default function Compare() {
  const [poseSelection, setPoseSelection] = useState<PoseSelection>("");
  const [dateX, setDateX] = useState("");
  const [dateY, setDateY] = useState("");
  const [mode, setMode] = useState<Mode>("side-by-side");
  const [opacity, setOpacity] = useState(50);
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
  function updateGridLine(index: number, value: number) {
    setGridLines((lines) => lines.map((l, i) => (i === index ? value : l)));
  }

  const isAllPoses = poseSelection === ALL_POSES;

  const posesQuery = useQuery({ queryKey: ["poses"], queryFn: api.poses.list });

  // Sobald eine einzelne Pose gewählt ist: alle Fotos dieser Pose laden, um
  // die Datums-Dropdowns auf die tatsächlich vorhandenen Tage zu
  // beschränken (statt einer freien Datumseingabe, bei der man leere Tage
  // treffen kann).
  const posePhotosQuery = useQuery({
    queryKey: ["photos", "by-pose", poseSelection],
    queryFn: () => api.photos.list({ pose_id: Number(poseSelection) }),
    enabled: typeof poseSelection === "number",
  });

  // "Alle Posen": alle zugeordneten Fotos laden (posenübergreifend), um
  // sowohl die Datums-Dropdowns zu befüllen als auch pro Pose das Bildpaar
  // für die zwei gewählten Termine client-seitig herauszusuchen.
  const allPhotosQuery = useQuery({
    queryKey: ["photos", "all-for-compare"],
    queryFn: () => api.photos.list(),
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
    queryKey: ["comparison", poseSelection, dateX, dateY],
    queryFn: () =>
      api.comparisons.get({ pose_id: Number(poseSelection), date_x: dateX, date_y: dateY }),
    enabled: typeof poseSelection === "number" && dateX !== "" && dateY !== "",
    retry: false,
  });

  const poses = posesQuery.data ?? [];
  const result = comparisonQuery.data;

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

  // KI-Judge-Analyse: läuft ausschließlich per Knopfdruck (siehe Button
  // unten), nie automatisch beim Auswählen von Pose/Datum - jeder Aufruf
  // kostet echte API-Anfragen. Zwei getrennte Mutations, je nachdem ob
  // eine Einzelpose oder "Alle Posen" gewählt ist.
  const aiAnalysisMutation = useMutation({
    mutationFn: () =>
      api.comparisons.aiAnalysis({ pose_id: Number(poseSelection), date_x: dateX, date_y: dateY }),
  });
  const aiAnalysisAllMutation = useMutation({
    mutationFn: () => api.comparisons.aiAnalysisAll({ date_x: dateX, date_y: dateY }),
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

  const resolveSrc = (photo: Photo) =>
    mediaUrl(normalize && photo.normalized_path ? photo.normalized_path : photo.display_path);

  const filterFor = (brightness: number) =>
    brightness === BRIGHTNESS_DEFAULT ? undefined : `brightness(${brightness}%)`;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-white">Compare</h1>

      <div className="flex flex-wrap items-end gap-4 rounded-xl border border-white/5 bg-surface p-4">
        <label className="flex flex-col gap-1 text-sm text-slate-400">
          Pose
          <select
            value={poseSelection}
            onChange={(e) =>
              setPoseSelection(
                e.target.value === "" ? "" : e.target.value === ALL_POSES ? ALL_POSES : Number(e.target.value)
              )
            }
            className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
          >
            <option value="">Pose wählen…</option>
            <option value={ALL_POSES}>Alle Posen</option>
            {poses.map((p, index) => (
              <option key={p.id} value={p.id}>
                {numberedPoseOptionLabel(index, p.name)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm text-slate-400">
          Datum X
          <select
            value={dateX}
            onChange={(e) => setDateX(e.target.value)}
            disabled={poseSelection === "" || availableDates.length === 0}
            className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none disabled:opacity-40"
          >
            <option value="">
              {poseSelection === "" ? "Erst Pose wählen…" : "Datum wählen…"}
            </option>
            {availableDates.map((d) => (
              <option key={d} value={d}>
                {formatDate(d)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm text-slate-400">
          Datum Y
          <select
            value={dateY}
            onChange={(e) => setDateY(e.target.value)}
            disabled={poseSelection === "" || availableDates.length === 0}
            className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none disabled:opacity-40"
          >
            <option value="">
              {poseSelection === "" ? "Erst Pose wählen…" : "Datum wählen…"}
            </option>
            {availableDates.map((d) => (
              <option key={d} value={d}>
                {formatDate(d)}
              </option>
            ))}
          </select>
        </label>
        {!isAllPoses && (
          <div className="flex gap-1 rounded-full bg-black/30 p-1">
            {(["side-by-side", "overlay", "slider"] as Mode[]).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
                  mode === m ? "bg-accent text-slate-900" : "text-slate-400 hover:text-white"
                }`}
              >
                {m === "side-by-side" ? "Side-by-Side" : m === "overlay" ? "Overlay" : "Schieberegler"}
              </button>
            ))}
          </div>
        )}
        <label className="flex items-center gap-2 pb-2 text-sm text-slate-300">
          <input
            type="checkbox"
            checked={normalize}
            onChange={(e) => setNormalize(e.target.checked)}
            className="h-4 w-4 accent-accent"
          />
          KI-Normalisierung (Ausrichtung &amp; Skalierung)
        </label>
        <label className="flex items-center gap-2 pb-2 text-sm text-slate-300">
          <input
            type="checkbox"
            checked={showGrid}
            onChange={(e) => setShowGrid(e.target.checked)}
            className="h-4 w-4 accent-accent"
          />
          Ausrichtungsgitter
        </label>
      </div>

      {!isAllPoses && comparisonQuery.isError && (
        <p className="text-red-400">
          Für mindestens eines der Daten existiert kein Foto dieser Pose.
        </p>
      )}

      {poseSelection !== "" && availableDates.length === 0 && !posePhotosQuery.isLoading && !allPhotosQuery.isLoading && (
        <p className="text-slate-500">
          {isAllPoses ? "Noch keine zugeordneten Fotos vorhanden." : "Für diese Pose sind noch keine Fotos zugeordnet."}
        </p>
      )}

      {isAllPoses && dateX !== "" && dateY !== "" && allPosePairs.length === 0 && (
        <p className="text-slate-500">Für keine Pose existieren Fotos an beiden gewählten Terminen.</p>
      )}

      {!isAllPoses && missingNormalized && (
        <p className="rounded-lg bg-yellow-500/10 px-3 py-2 text-sm text-yellow-400">
          Für mindestens eines der Bilder ist keine normalisierte Version vorhanden
          (Normalisierung fehlgeschlagen oder ausstehend) — es wird das Originalbild angezeigt.
        </p>
      )}

      {poses.length > 0 && (
        <PoseNavBar poses={poses} currentPoseId={poseSelection} onNavigate={goToPose} disabled={isAllPoses} />
      )}

      {((isAllPoses && allPosePairs.length > 0) || (!isAllPoses && result)) && (
        <div className="flex flex-col items-center gap-2">
          <button
            onClick={() => activeAiMutation.mutate()}
            disabled={activeAiMutation.isPending}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {activeAiMutation.isPending
              ? "Judge analysiert…"
              : isAllPoses
                ? `🥊 KI-Gesamtanalyse (${allPosePairs.length} Posen)`
                : "🥊 KI-Analyse (Judge-Bewertung)"}
          </button>
          {activeAiMutation.isPending && (
            <p className="flex items-center gap-2 text-xs text-slate-400">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-accent" />
              KI arbeitet noch… {elapsedSeconds}s
              {elapsedSeconds > 20 && " (bei Serverüberlastung versucht Gemini automatisch erneut)"}
            </p>
          )}
        </div>
      )}

      {activeAiMutation.isError && (
        <p className="rounded-lg bg-red-500/10 px-3 py-2 text-sm text-red-400">
          {(activeAiMutation.error as { response?: { data?: { detail?: string } } })?.response
            ?.data?.detail ?? "KI-Analyse fehlgeschlagen."}
        </p>
      )}

      {activeAiMutation.data && <JudgeAnalysis text={activeAiMutation.data.analysis} />}

      {!isAllPoses && result && mode === "side-by-side" && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <ComparePane
            label={formatDate(dateX)}
            src={resolveSrc(result.photo_x)}
            filter={filterFor(brightnessX)}
            brightness={brightnessX}
            onBrightnessChange={setBrightnessX}
            showGrid={showGrid}
            gridLines={gridLines}
            onGridLineChange={updateGridLine}
          />
          <ComparePane
            label={formatDate(dateY)}
            src={resolveSrc(result.photo_y)}
            filter={filterFor(brightnessY)}
            brightness={brightnessY}
            onBrightnessChange={setBrightnessY}
            showGrid={showGrid}
            gridLines={gridLines}
            onGridLineChange={updateGridLine}
          />
        </div>
      )}

      {!isAllPoses && result && mode === "overlay" && (
        <div className="space-y-4">
          {!normalize && (
            <p className="rounded-lg bg-yellow-500/10 px-3 py-2 text-sm text-yellow-400">
              Ohne KI-Normalisierung stimmen Kameraabstand/-neigung zwischen den Fotos meist
              nicht überein — für ein aussagekräftiges Overlay die Checkbox oben aktivieren.
            </p>
          )}
          <OverlayPane
            key={`${result.photo_x.id}-${result.photo_y.id}`}
            srcX={resolveSrc(result.photo_x)}
            srcY={resolveSrc(result.photo_y)}
            filterX={filterFor(brightnessX)}
            filterY={filterFor(brightnessY)}
            opacity={opacity}
            altX={formatDate(dateX)}
            altY={formatDate(dateY)}
            showGrid={showGrid}
            gridLines={gridLines}
            onGridLineChange={updateGridLine}
          />

          <div className="mx-auto max-w-md rounded-xl border border-white/5 bg-surface p-4">
            <SliderControl
              icon="◐"
              label={`Deckkraft ${formatDate(dateY)}`}
              value={opacity}
              min={0}
              max={100}
              step={1}
              onChange={setOpacity}
              suffix="%"
            />
          </div>

          <div className="mx-auto grid max-w-md grid-cols-1 gap-x-6 gap-y-4 rounded-xl border border-white/5 bg-surface p-4 sm:grid-cols-2">
            <BrightnessSlider
              value={brightnessX}
              onChange={setBrightnessX}
            />
            <BrightnessSlider
              value={brightnessY}
              onChange={setBrightnessY}
            />
          </div>
        </div>
      )}

      {!isAllPoses && result && mode === "slider" && (
        <div className="space-y-4">
          {!normalize && (
            <p className="rounded-lg bg-yellow-500/10 px-3 py-2 text-sm text-yellow-400">
              Ohne KI-Normalisierung stimmen Kameraabstand/-neigung zwischen den Fotos meist
              nicht überein — für einen sauberen Schieberegler-Vergleich die Checkbox oben
              aktivieren.
            </p>
          )}
          <SliderComparePane
            key={`${result.photo_x.id}-${result.photo_y.id}`}
            srcX={resolveSrc(result.photo_x)}
            srcY={resolveSrc(result.photo_y)}
            filterX={filterFor(brightnessX)}
            filterY={filterFor(brightnessY)}
            altX={formatDate(dateX)}
            altY={formatDate(dateY)}
            showGrid={showGrid}
            gridLines={gridLines}
            onGridLineChange={updateGridLine}
          />
          <div className="mx-auto grid max-w-2xl grid-cols-1 gap-x-8 gap-y-4 rounded-xl border border-white/5 bg-surface p-4 sm:grid-cols-2">
            <BrightnessSlider
              value={brightnessX}
              onChange={setBrightnessX}
            />
            <BrightnessSlider
              value={brightnessY}
              onChange={setBrightnessY}
            />
          </div>
        </div>
      )}

      {isAllPoses && allPosePairs.length > 0 && (
        <div className="space-y-8">
          <div className="mx-auto grid max-w-md grid-cols-1 gap-x-6 gap-y-4 rounded-xl border border-white/5 bg-surface p-4 sm:grid-cols-2">
            <BrightnessSlider value={brightnessX} onChange={setBrightnessX} />
            <BrightnessSlider value={brightnessY} onChange={setBrightnessY} />
          </div>
          {allPosePairs.map(({ pose, photoX, photoY }) => (
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
                  showBrightnessSlider={false}
                  showGrid={showGrid}
                  gridLines={gridLines}
                  onGridLineChange={updateGridLine}
                />
              </div>
            </section>
          ))}
        </div>
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

function PoseNavBar({
  poses,
  currentPoseId,
  onNavigate,
  disabled,
}: {
  poses: Pose[];
  currentPoseId: PoseSelection;
  onNavigate: (delta: number) => void;
  disabled?: boolean;
}) {
  const currentIndex = poses.findIndex((p) => p.id === currentPoseId);
  const currentPose = currentIndex >= 0 ? poses[currentIndex] : undefined;
  const label =
    currentPoseId === ALL_POSES
      ? "Alle Posen"
      : currentPose
        ? numberedPoseOptionLabel(currentIndex, currentPose.name)
        : "Pose wählen…";
  return (
    <div className="flex items-center justify-center gap-4">
      <button
        onClick={() => onNavigate(-1)}
        disabled={disabled}
        aria-label="Vorherige Pose"
        className="flex h-9 w-9 items-center justify-center rounded-full bg-surface text-slate-300 transition-colors hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-30"
      >
        ‹
      </button>
      <span className="min-w-[10rem] text-center text-sm font-medium text-slate-300">{label}</span>
      <button
        onClick={() => onNavigate(1)}
        disabled={disabled}
        aria-label="Nächste Pose"
        className="flex h-9 w-9 items-center justify-center rounded-full bg-surface text-slate-300 transition-colors hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-30"
      >
        ›
      </button>
    </div>
  );
}

/** Belichtungs-Slider unter einem Bild - jedes Bild wird individuell
 * gesteuert (100% = unverändertes Original). */
function BrightnessSlider({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  return (
    <SliderControl
      icon="☀"
      label="Belichtung"
      value={value}
      min={BRIGHTNESS_MIN}
      max={BRIGHTNESS_MAX}
      step={1}
      onChange={onChange}
      suffix="%"
    />
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
function ZoomPane({
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
}: {
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
}) {
  const { scale, translate, containerRef, isDragging, reset, setScaleFromSlider } = usePanZoom();
  const [rotation, setRotation] = useState(0);

  return (
    <div>
      <div
        ref={containerRef}
        className="relative aspect-[3/4] w-full overflow-hidden bg-black/40"
        style={{ cursor: scale > 1 ? (isDragging ? "grabbing" : "grab") : "zoom-in" }}
        onDoubleClick={reset}
        title="Mausrad zum Zoomen, bei Zoom Klick+Ziehen zum Verschieben, Doppelklick zum Zurücksetzen"
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
        {scale > 1 && (
          <span className="pointer-events-none absolute bottom-1 right-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-slate-200">
            {scale.toFixed(2)}×
          </span>
        )}
      </div>
      <div className="space-y-4 p-3.5">
        {caption && <p className="text-sm font-medium text-slate-300">{caption}</p>}
        <ZoomSlider scale={scale} onChange={setScaleFromSlider} />
        <RotationSlider degrees={rotation} onChange={setRotation} />
        {showBrightnessSlider && brightness !== undefined && onBrightnessChange && (
          <BrightnessSlider value={brightness} onChange={onBrightnessChange} />
        )}
      </div>
    </div>
  );
}

/** Overlay-Variante: beide Bilder liegen übereinander und werden beim
 * Zoomen/Verschieben gemeinsam transformiert (sonst würden sie
 * auseinanderdriften). Neigung bleibt pro Bild eigenständig einstellbar
 * (Kamera-Tilt ist eine Eigenschaft der jeweiligen Aufnahme, kein
 * gemeinsamer Wert). */
function OverlayPane({
  srcX,
  srcY,
  filterX,
  filterY,
  opacity,
  altX,
  altY,
  showGrid,
  gridLines,
  onGridLineChange,
}: {
  srcX: string;
  srcY: string;
  filterX: string | undefined;
  filterY: string | undefined;
  opacity: number;
  altX: string;
  altY: string;
  showGrid?: boolean;
  gridLines?: number[];
  onGridLineChange?: (index: number, value: number) => void;
}) {
  const { scale, translate, containerRef, isDragging, reset, setScaleFromSlider } = usePanZoom();
  const [rotationX, setRotationX] = useState(0);
  const [rotationY, setRotationY] = useState(0);

  return (
    <div className="space-y-3">
      <div
        ref={containerRef}
        className="relative mx-auto aspect-[3/4] max-w-md overflow-hidden rounded-xl border border-white/5 bg-black/40"
        style={{ cursor: scale > 1 ? (isDragging ? "grabbing" : "grab") : "zoom-in" }}
        onDoubleClick={reset}
        title="Mausrad zum Zoomen, bei Zoom Klick+Ziehen zum Verschieben, Doppelklick zum Zurücksetzen"
      >
        <div className="absolute inset-0" style={transformStyle(translate, scale)}>
          <img
            src={srcX}
            alt={altX}
            draggable={false}
            className="h-full w-full object-cover"
            style={{ filter: filterX, transform: `rotate(${rotationX}deg)` }}
          />
        </div>
        <div className="absolute inset-0" style={transformStyle(translate, scale)}>
          <img
            src={srcY}
            alt={altY}
            draggable={false}
            className="h-full w-full object-cover"
            style={{ opacity: opacity / 100, filter: filterY, transform: `rotate(${rotationY}deg)` }}
          />
        </div>
        {showGrid && gridLines && onGridLineChange && (
          <AlignmentGridOverlay lines={gridLines} onChange={onGridLineChange} />
        )}
        {scale > 1 && (
          <span className="pointer-events-none absolute bottom-1 right-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-slate-200">
            {scale.toFixed(2)}×
          </span>
        )}
      </div>
      <div className="mx-auto max-w-md space-y-4 rounded-xl border border-white/5 bg-surface p-4">
        <ZoomSlider scale={scale} onChange={setScaleFromSlider} />
        <div className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2">
          <RotationSlider label={`Neigung ${altX}`} degrees={rotationX} onChange={setRotationX} />
          <RotationSlider label={`Neigung ${altY}`} degrees={rotationY} onChange={setRotationY} />
        </div>
      </div>
    </div>
  );
}

/** Schieberegler-Vergleich: eine vertikale Trennlinie, die man horizontal
 * hin- und herziehen kann - links Bild X, rechts Bild Y (klassischer
 * Vorher/Nachher-Slider). Besonders bei geraden Posen (z.B. Front
 * Relaxed) hilfreich, um exakt dieselbe Körperstelle direkt nebeneinander
 * zu sehen. Zoom/Pan wirken auf beide Bilder gleich (siehe usePanZoom),
 * damit sie beim Zoomen deckungsgleich bleiben; ein zusätzlicher
 * Zoom-Slider erlaubt feinstufiges Nachjustieren über das Mausrad hinaus. */
function SliderComparePane({
  srcX,
  srcY,
  filterX,
  filterY,
  altX,
  altY,
  showGrid,
  gridLines,
  onGridLineChange,
}: {
  srcX: string;
  srcY: string;
  filterX: string | undefined;
  filterY: string | undefined;
  altX: string;
  altY: string;
  showGrid?: boolean;
  gridLines?: number[];
  onGridLineChange?: (index: number, value: number) => void;
}) {
  const { scale, translate, containerRef, isDragging, reset, setScaleFromSlider } = usePanZoom();
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
        className="relative mx-auto aspect-[3/4] max-w-md overflow-hidden rounded-xl border border-white/5 bg-black/40 select-none"
        style={{ cursor: scale > 1 ? (isDragging ? "grabbing" : "grab") : "default" }}
        onDoubleClick={reset}
        title="Mausrad zum Zoomen, bei Zoom Klick+Ziehen zum Verschieben, Trennlinie ziehen zum Vergleichen"
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
        {scale > 1 && (
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
      <div className="mx-auto max-w-2xl space-y-5 rounded-xl border border-white/5 bg-surface p-4">
        <ZoomSlider label="Zoom (gemeinsam)" scale={scale} onChange={setScaleFromSlider} />
        <div className="grid grid-cols-1 gap-x-8 gap-y-5 border-t border-white/5 pt-5 sm:grid-cols-2">
          <div className="space-y-4">
            <p className="text-sm font-medium text-slate-300">{altX}</p>
            <ZoomSlider label="Zoom" scale={fineZoomX} onChange={setFineZoomX} />
            <RotationSlider degrees={rotationX} onChange={setRotationX} />
            <PositionSlider offset={offsetX} onChange={setOffsetX} />
          </div>
          <div className="space-y-4">
            <p className="text-sm font-medium text-slate-300">{altY}</p>
            <ZoomSlider label="Zoom" scale={fineZoomY} onChange={setFineZoomY} />
            <RotationSlider degrees={rotationY} onChange={setRotationY} />
            <PositionSlider offset={offsetY} onChange={setOffsetY} />
          </div>
        </div>
      </div>
    </div>
  );
}

function ComparePane({
  label,
  src,
  filter,
  brightness,
  onBrightnessChange,
  showBrightnessSlider = true,
  showGrid,
  gridLines,
  onGridLineChange,
}: {
  label: string;
  src: string;
  filter: string | undefined;
  brightness: number;
  onBrightnessChange: (value: number) => void;
  showBrightnessSlider?: boolean;
  showGrid?: boolean;
  gridLines?: number[];
  onGridLineChange?: (index: number, value: number) => void;
}) {
  return (
    <figure className="overflow-hidden rounded-xl border border-white/5 bg-surface">
      <ZoomPane
        key={src}
        src={src}
        alt={label}
        filter={filter}
        caption={label}
        brightness={brightness}
        onBrightnessChange={onBrightnessChange}
        showBrightnessSlider={showBrightnessSlider}
        showGrid={showGrid}
        gridLines={gridLines}
        onGridLineChange={onGridLineChange}
      />
    </figure>
  );
}
