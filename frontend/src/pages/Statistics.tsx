import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import { formatDateShortWithWeek } from "../utils/date";
import PageHeader from "../components/PageHeader";
import { useTimelineVisibleDates } from "../hooks/useTimelineVisibleDates";

type RangeKey = "1m" | "3m" | "6m" | "1y" | "all";

const RANGE_OPTIONS: { key: RangeKey; label: string; days: number | null }[] = [
  { key: "1m", label: "1 Month", days: 30 },
  { key: "3m", label: "3 Months", days: 90 },
  { key: "6m", label: "6 Months", days: 182 },
  { key: "1y", label: "1 Year", days: 365 },
  { key: "all", label: "All", days: null },
];

const CHART_WIDTH = 900;
const CHART_HEIGHT = 320;
const PADDING = { top: 20, right: 20, bottom: 32, left: 48 };

export default function Statistics() {
  const { clientId } = useParams<{ clientId: string }>();
  const clientIdNum = Number(clientId);
  const [range, setRange] = useState<RangeKey>("3m");

  const dayLogsQuery = useQuery({
    queryKey: ["day-logs", clientIdNum],
    queryFn: () => api.dayLogs.list(clientIdNum),
  });
  const { visibleDates, isLoading: photosLoading } = useTimelineVisibleDates(clientIdNum);

  const points = useMemo(() => {
    // Nur Gewichte von Tagen mit mindestens einem Timeline-sichtbaren Foto
    // (siehe useTimelineVisibleDates) - ein gelöschter/noch nicht
    // freigegebener Check-in soll sein Gewicht hier verschwinden lassen,
    // auch wenn der DayLog-Eintrag selbst unverändert bleibt.
    const withWeight = (dayLogsQuery.data ?? [])
      .filter((d) => d.weight_kg != null && visibleDates.has(d.date))
      .map((d) => ({ date: d.date, weight: d.weight_kg as number }))
      .sort((a, b) => (a.date < b.date ? -1 : 1));

    const days = RANGE_OPTIONS.find((r) => r.key === range)?.days ?? null;
    if (days == null || withWeight.length === 0) return withWeight;

    const latest = new Date(withWeight[withWeight.length - 1].date);
    const cutoff = new Date(latest);
    cutoff.setDate(cutoff.getDate() - days);
    const cutoffIso = cutoff.toISOString().slice(0, 10);
    return withWeight.filter((p) => p.date >= cutoffIso);
  }, [dayLogsQuery.data, range, visibleDates]);

  if (dayLogsQuery.isLoading || photosLoading) {
    return (
      <>
        <PageHeader title="Statistics" />
        <p className="text-slate-500">Loading statistics…</p>
      </>
    );
  }
  if (dayLogsQuery.isError) {
    return (
      <>
        <PageHeader title="Statistics" />
        <p className="text-red-400">Statistics could not be loaded.</p>
      </>
    );
  }

  const totalWeighed = (dayLogsQuery.data ?? []).filter(
    (d) => d.weight_kg != null && visibleDates.has(d.date)
  ).length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Statistics"
        actions={
          <div className="flex gap-1 rounded-full bg-surface p-1">
            {RANGE_OPTIONS.map((opt) => (
              <button
                key={opt.key}
                onClick={() => setRange(opt.key)}
                className={`rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
                  range === opt.key
                    ? "bg-accent text-slate-900"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        }
      />

      {totalWeighed === 0 ? (
        <div className="rounded-xl border border-white/5 bg-surface p-8 text-center text-slate-400">
          No weight data recorded yet. Add a weight while assigning a photo
          (Unprocessed) or later on the Timeline page.
        </div>
      ) : points.length === 0 ? (
        <div className="rounded-xl border border-white/5 bg-surface p-8 text-center text-slate-400">
          No weight data available for the selected time range. Choose a longer range.
        </div>
      ) : (
        <>
          <div className="rounded-xl border border-white/5 bg-surface p-4 sm:p-6">
            <WeightChart points={points} />
          </div>
          <SummaryStats points={points} />
        </>
      )}
    </div>
  );
}

function SummaryStats({ points }: { points: { date: string; weight: number }[] }) {
  const first = points[0];
  const last = points[points.length - 1];
  const delta = last.weight - first.weight;
  const min = Math.min(...points.map((p) => p.weight));
  const max = Math.max(...points.map((p) => p.weight));

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <StatTile label="Current" value={`${last.weight.toFixed(1)} kg`} />
      <StatTile
        label="Change"
        value={`${delta >= 0 ? "+" : ""}${delta.toFixed(1)} kg`}
        accent={delta === 0 ? undefined : delta > 0 ? "up" : "down"}
      />
      <StatTile label="Minimum" value={`${min.toFixed(1)} kg`} />
      <StatTile label="Maximum" value={`${max.toFixed(1)} kg`} />
    </div>
  );
}

function StatTile({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: "up" | "down";
}) {
  const color =
    accent === "up" ? "text-red-400" : accent === "down" ? "text-emerald-400" : "text-white";
  return (
    <div className="rounded-xl border border-white/5 bg-surface p-4">
      <p className="text-xs text-slate-500">{label}</p>
      <p className={`mt-1 text-lg font-semibold ${color}`}>{value}</p>
    </div>
  );
}

function WeightChart({ points }: { points: { date: string; weight: number }[] }) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const weights = points.map((p) => p.weight);
  const minWeight = Math.min(...weights);
  const maxWeight = Math.max(...weights);
  // Etwas Puffer oben/unten, damit die Linie nicht am Rand klebt; bei
  // konstantem Gewicht (min===max) trotzdem eine sichtbare Spanne erzeugen.
  const span = Math.max(maxWeight - minWeight, 1);
  const yMin = minWeight - span * 0.15;
  const yMax = maxWeight + span * 0.15;

  const plotWidth = CHART_WIDTH - PADDING.left - PADDING.right;
  const plotHeight = CHART_HEIGHT - PADDING.top - PADDING.bottom;

  const x = (i: number) =>
    PADDING.left + (points.length === 1 ? plotWidth / 2 : (i / (points.length - 1)) * plotWidth);
  const y = (weight: number) =>
    PADDING.top + plotHeight - ((weight - yMin) / (yMax - yMin)) * plotHeight;

  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"} ${x(i)} ${y(p.weight)}`).join(" ");
  const areaPath = `${linePath} L ${x(points.length - 1)} ${PADDING.top + plotHeight} L ${x(0)} ${PADDING.top + plotHeight} Z`;

  const yTicks = 4;
  const tickValues = Array.from({ length: yTicks + 1 }, (_, i) => yMin + ((yMax - yMin) / yTicks) * i);

  // Nicht jedes Datum beschriften - sonst überlappt es bei vielen Punkten.
  const maxLabels = 6;
  const labelStep = Math.max(1, Math.ceil(points.length / maxLabels));

  return (
    <div className="w-full overflow-x-auto">
      <svg
        viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
        className="w-full min-w-[600px]"
        role="img"
        aria-label="Weight trend over time"
      >
        {/* Horizontale Gitterlinien + Y-Achsenbeschriftung */}
        {tickValues.map((v, i) => (
          <g key={i}>
            <line
              x1={PADDING.left}
              x2={CHART_WIDTH - PADDING.right}
              y1={y(v)}
              y2={y(v)}
              stroke="rgba(255,255,255,0.08)"
            />
            <text x={PADDING.left - 8} y={y(v)} textAnchor="end" dominantBaseline="middle" className="fill-slate-500 text-[10px]">
              {v.toFixed(0)}
            </text>
          </g>
        ))}

        {/* Fläche unter der Linie */}
        <path d={areaPath} fill="url(#weightGradient)" opacity={0.25} />
        <defs>
          <linearGradient id="weightGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.6} />
            <stop offset="100%" stopColor="#22d3ee" stopOpacity={0} />
          </linearGradient>
        </defs>

        {/* Linie */}
        <path d={linePath} fill="none" stroke="#22d3ee" strokeWidth={2} />

        {/* Datenpunkte + X-Achsenbeschriftung (kein eigenes Hover-Handling
            mehr pro Punkt - siehe die durchgehende Hover-Fläche unten). */}
        {points.map((p, i) => (
          <g key={p.date}>
            <circle cx={x(i)} cy={y(p.weight)} r={hoverIndex === i ? 5 : 3} fill="#22d3ee" />
            {i % labelStep === 0 && (
              <text
                x={x(i)}
                y={CHART_HEIGHT - 8}
                textAnchor="middle"
                className="fill-slate-500 text-[10px]"
              >
                {new Date(p.date).toLocaleDateString("en-US", { day: "2-digit", month: "2-digit" })}
              </text>
            )}
          </g>
        ))}

        {/* Eine einzige durchgehende Hover-Fläche über der ganzen Plot-
            Fläche statt vieler schmaler Einzel-Rechtecke pro Punkt (siehe
            Bugreport "Mouseover funktioniert nur sporadisch"): bei eng
            beieinanderliegenden Punkten überlappte das eingeblendete
            Tooltip (foreignObject) teilweise die Hover-Fläche des
            Nachbarpunkts und fing dessen Mausereignisse ab, was das Hover
            wechselweise abbrechen ließ. onMouseMove bestimmt stattdessen
            fortlaufend den nächstgelegenen Punkt zur Mausposition -
            robust unabhängig vom Punktabstand, keine Lücken/Überlappung. */}
        <rect
          x={PADDING.left}
          y={PADDING.top}
          width={plotWidth}
          height={plotHeight}
          fill="transparent"
          onMouseMove={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const relativeX = ((e.clientX - rect.left) / rect.width) * plotWidth;
            const svgX = PADDING.left + relativeX;
            let closest = 0;
            let closestDist = Infinity;
            points.forEach((_, i) => {
              const dist = Math.abs(x(i) - svgX);
              if (dist < closestDist) {
                closestDist = dist;
                closest = i;
              }
            });
            setHoverIndex(closest);
          }}
          onMouseLeave={() => setHoverIndex(null)}
        />

        {/* Tooltip - pointer-events: none, damit es selbst niemals die
            durchgehende Hover-Fläche darunter blockiert. */}
        {hoverIndex != null && (
          <g style={{ pointerEvents: "none" }}>
            <line
              x1={x(hoverIndex)}
              x2={x(hoverIndex)}
              y1={PADDING.top}
              y2={PADDING.top + plotHeight}
              stroke="rgba(255,255,255,0.2)"
            />
            <foreignObject
              x={Math.min(Math.max(x(hoverIndex) - 100, 0), CHART_WIDTH - 200)}
              y={Math.max(y(points[hoverIndex].weight) - 52, 0)}
              width={200}
              height={48}
              // Die alte feste Breite (120px) reichte für Text wie
              // "Fr., 27. Feb. 2026 · KW 9" nicht aus - er ist umgebrochen
              // und wurde durch die feste foreignObject-Höhe abgeschnitten
              // (siehe Bugreport-Screenshot). Breiter + whitespace-nowrap
              // hält ihn einzeilig; overflow:visible als Sicherheitsnetz,
              // falls ein Datum trotzdem mal breiter als 200px wird.
              style={{ overflow: "visible" }}
            >
              <div className="whitespace-nowrap rounded-lg bg-black/80 px-2 py-1 text-center text-xs text-white">
                <div className="font-semibold">{points[hoverIndex].weight.toFixed(1)} kg</div>
                <div className="text-slate-400">{formatDateShortWithWeek(points[hoverIndex].date)}</div>
              </div>
            </foreignObject>
          </g>
        )}
      </svg>
    </div>
  );
}
