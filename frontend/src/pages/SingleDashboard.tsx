// frontend/src/pages/SingleDashboard.tsx
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import PageHeader from "../components/PageHeader";
import { Card } from "../components/Card";

type RangeKey = "1m" | "3m" | "6m" | "1y" | "all";

const RANGE_OPTIONS: { key: RangeKey; label: string; days: number | null }[] = [
  { key: "1m", label: "1 Month", days: 30 },
  { key: "3m", label: "3 Months", days: 90 },
  { key: "6m", label: "6 Months", days: 182 },
  { key: "1y", label: "1 Year", days: 365 },
  { key: "all", label: "All", days: null },
];

export default function SingleDashboard() {
  const { clientId } = useParams<{ clientId: string }>();
  const clientIdNum = Number(clientId);

  const dayLogsQuery = useQuery({
    queryKey: ["day-logs", clientIdNum],
    queryFn: () => api.dayLogs.list(clientIdNum),
    enabled: !!clientId,
  });

  const weighedPoints = useMemo(() => {
    return (dayLogsQuery.data ?? [])
      .filter((d) => d.weight_kg != null)
      .map((d) => ({ date: d.date, weight: d.weight_kg as number }))
      .sort((a, b) => (a.date < b.date ? -1 : 1));
  }, [dayLogsQuery.data]);

  return (
    <div>
      <PageHeader title="Dashboard" />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <WeightTrendWidget points={weighedPoints} isLoading={dayLogsQuery.isLoading} />
        <RecentEntriesWidget points={weighedPoints} isLoading={dayLogsQuery.isLoading} />
        <ProgressWidget points={weighedPoints} isLoading={dayLogsQuery.isLoading} />
        <QuickActionsWidget clientId={clientIdNum} />
      </div>
    </div>
  );
}

function WeightTrendWidget({
  points,
  isLoading,
}: {
  points: { date: string; weight: number }[];
  isLoading: boolean;
}) {
  const [range, setRange] = useState<RangeKey>("3m");

  const filtered = useMemo(() => {
    const days = RANGE_OPTIONS.find((r) => r.key === range)?.days ?? null;
    if (days == null || points.length === 0) return points;
    const latest = new Date(points[points.length - 1].date);
    const cutoff = new Date(latest);
    cutoff.setDate(cutoff.getDate() - days);
    const cutoffIso = cutoff.toISOString().slice(0, 10);
    return points.filter((p) => p.date >= cutoffIso);
  }, [points, range]);

  return (
    <Card title="Weight trend">
      <div className="mb-3 flex flex-wrap gap-1">
        {RANGE_OPTIONS.map((opt) => (
          <button
            key={opt.key}
            onClick={() => setRange(opt.key)}
            className={`rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
              range === opt.key
                ? "bg-accent text-slate-900"
                : "bg-black/30 text-slate-400 hover:text-white"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {!isLoading && filtered.length < 2 && (
        <p className="text-sm text-slate-500">Not enough data yet.</p>
      )}
      {!isLoading && filtered.length >= 2 && <WeightSparkline points={filtered} />}
    </Card>
  );
}

function WeightSparkline({ points }: { points: { date: string; weight: number }[] }) {
  const width = 300;
  const height = 60;
  const weights = points.map((p) => p.weight);
  const minWeight = Math.min(...weights);
  const maxWeight = Math.max(...weights);
  const range = maxWeight - minWeight || 1;

  const coords = points.map((p, i) => {
    const x = (i / (points.length - 1)) * width;
    const y = height - ((p.weight - minWeight) / range) * height;
    return `${x},${y}`;
  });

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-16 w-full">
      <polyline points={coords.join(" ")} fill="none" stroke="#22d3ee" strokeWidth="2" />
    </svg>
  );
}

function RecentEntriesWidget({
  points,
  isLoading,
}: {
  points: { date: string; weight: number }[];
  isLoading: boolean;
}) {
  const recent = [...points].reverse().slice(0, 5);

  return (
    <Card title="Recent entries">
      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {!isLoading && recent.length === 0 && (
        <p className="text-sm text-slate-500">No weight entries yet.</p>
      )}
      <div className="max-h-64 space-y-1 overflow-y-auto">
        {recent.map((entry) => (
          <div
            key={entry.date}
            className="flex items-center justify-between rounded-lg px-2 py-1.5 text-sm text-slate-300"
          >
            <span>{new Date(entry.date).toLocaleDateString("en-US")}</span>
            <span className="text-slate-400">{entry.weight} kg</span>
          </div>
        ))}
      </div>
    </Card>
  );
}

function ProgressWidget({
  points,
  isLoading,
}: {
  points: { date: string; weight: number }[];
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <Card title="Progress">
        <p className="text-sm text-slate-500">Loading…</p>
      </Card>
    );
  }
  if (points.length === 0) {
    return (
      <Card title="Progress">
        <p className="text-sm text-slate-500">No weight entries yet.</p>
      </Card>
    );
  }

  const first = points[0];
  const last = points[points.length - 1];
  const delta = last.weight - first.weight;
  const max = Math.max(...points.map((p) => p.weight));

  return (
    <Card title="Progress">
      <div className="grid grid-cols-3 gap-2">
        <div>
          <p className="text-xl font-medium text-accent">{last.weight.toFixed(1)}</p>
          <p className="text-xs text-slate-500">current kg</p>
        </div>
        <div>
          <p className="text-xl font-medium text-accent">
            {delta > 0 ? "+" : ""}
            {delta.toFixed(1)}
          </p>
          <p className="text-xs text-slate-500">since start</p>
        </div>
        <div>
          <p className="text-xl font-medium text-accent">{max.toFixed(1)}</p>
          <p className="text-xs text-slate-500">max kg</p>
        </div>
      </div>
    </Card>
  );
}

function QuickActionsWidget({ clientId }: { clientId: number }) {
  return (
    <Card title="Quick actions">
      <div className="flex flex-col gap-2">
        <Link
          to={`/clients/${clientId}/unprocessed`}
          className="rounded-lg border border-white/10 px-4 py-2 text-sm font-medium text-white hover:bg-white/5"
        >
          Upload photos
        </Link>
        <Link
          to={`/clients/${clientId}/compare`}
          className="rounded-lg border border-white/10 px-4 py-2 text-sm font-medium text-white hover:bg-white/5"
        >
          Compare
        </Link>
      </div>
    </Card>
  );
}
