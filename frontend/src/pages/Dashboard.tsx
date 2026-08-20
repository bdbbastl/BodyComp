// frontend/src/pages/Dashboard.tsx
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import PageHeader from "../components/PageHeader";
import { Card } from "../components/Card";
import { UpgradeBanner } from "../components/UpgradeBanner";
import { Avatar } from "../components/Avatar";
import { Sparkline } from "../components/Sparkline";
import { useCurrentUser } from "../hooks/useCurrentUser";
import { useOnboarding } from "../contexts/OnboardingContext";
import type {
  ActivityItem,
  Client,
  CoachDashboardSummary,
  NeedsAttentionClient,
  PendingCheckinSummary,
} from "../types";

function greetingForHour(hour: number): string {
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export default function Dashboard() {
  const queryClient = useQueryClient();
  const { data: user } = useCurrentUser();
  const { phase, stepIndex, steps, nextStep } = useOnboarding();
  const navigate = useNavigate();
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [heightCm, setHeightCm] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [gender, setGender] = useState("");
  const [startDate, setStartDate] = useState("");

  const clientsQuery = useQuery({ queryKey: ["clients"], queryFn: api.clients.list });
  const summaryQuery = useQuery({
    queryKey: ["dashboard", "coach-summary"],
    queryFn: api.dashboard.coachSummary,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      api.clients.create({
        name,
        height_cm: heightCm.trim() === "" ? null : Number(heightCm),
        birth_date: birthDate.trim() === "" ? null : birthDate,
        gender: gender.trim() === "" ? null : gender,
        start_date: startDate.trim() === "" ? null : startDate,
      }),
    onSuccess: (createdClient) => {
      queryClient.invalidateQueries({ queryKey: ["clients"] });
      setShowForm(false);
      setName("");
      setHeightCm("");
      setBirthDate("");
      setGender("");
      setStartDate("");

      if (phase === "tour" && steps[stepIndex]?.id === "new-client") {
        nextStep();
        navigate(`/clients/${createdClient.id}/settings`);
      }
    },
  });

  const clients = clientsQuery.data ?? [];

  const greeting = greetingForHour(new Date().getHours());
  const activeClientsCount = summaryQuery.data?.week_stats.active_clients ?? 0;
  const checkinsThisWeek = summaryQuery.data?.week_stats.checkins ?? 0;

  return (
    <div>
      <PageHeader
        title={user ? `${greeting}, ${user.display_name}` : "My Clients"}
        description={
          summaryQuery.data
            ? `${activeClientsCount} active client${activeClientsCount === 1 ? "" : "s"} · ${checkinsThisWeek} check-in${checkinsThisWeek === 1 ? "" : "s"} this week`
            : undefined
        }
        actions={
          <button
            data-tour="dashboard-new-client"
            onClick={() => setShowForm((s) => !s)}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90"
          >
            Add New Client
          </button>
        }
      />

      {user?.account_type === "coach" &&
        !["trialing", "active"].includes(user.subscription_status ?? "") &&
        clients.length >= 1 && (
          <div className="mb-4">
            <UpgradeBanner message="You're already using one client for free — you'll need a subscription for more." />
          </div>
        )}

      {showForm && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim()) createMutation.mutate();
          }}
          className="mb-6 grid grid-cols-1 gap-3 rounded-xl border border-white/5 bg-surface p-4 sm:grid-cols-2"
        >
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Name
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Height (cm)
            <input
              type="number"
              value={heightCm}
              onChange={(e) => setHeightCm(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Date of Birth
            <input
              type="date"
              value={birthDate}
              onChange={(e) => setBirthDate(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Gender
            <input
              value={gender}
              onChange={(e) => setGender(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Start Date
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          {(createMutation.error as any)?.response?.status === 402 && (
            <p className="text-sm text-red-400 sm:col-span-2">
              Client limit reached -{" "}
              <Link to="/account" className="underline">
                subscribe/upgrade
              </Link>
              {" "}to add more clients.
            </p>
          )}
          <div className="flex items-end">
            <button
              type="submit"
              disabled={!name.trim() || createMutation.isPending}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-40"
            >
              {createMutation.isPending ? "Adding…" : "Add"}
            </button>
          </div>
        </form>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <ClientsWidget clients={clients} isLoading={clientsQuery.isLoading} />
        <PendingCheckinsWidget
          items={summaryQuery.data?.pending_checkins ?? []}
          isLoading={summaryQuery.isLoading}
        />
        <NeedsAttentionWidget
          items={summaryQuery.data?.needs_attention ?? []}
          isLoading={summaryQuery.isLoading}
        />
        <WeekStatsWidget
          stats={summaryQuery.data?.week_stats}
          activeClientsLast7Days={(summaryQuery.data?.active_clients_last_7_days ?? []).map((d) => d.count)}
          isLoading={summaryQuery.isLoading}
        />
        <ActivityFeedWidget items={summaryQuery.data?.activity_feed ?? []} isLoading={summaryQuery.isLoading} />
        <WeeklyCheckinsChartWidget
          weeks={summaryQuery.data?.checkins_per_week ?? []}
          isLoading={summaryQuery.isLoading}
        />
      </div>
    </div>
  );
}

function ClientsWidget({ clients, isLoading }: { clients: Client[]; isLoading: boolean }) {
  const [search, setSearch] = useState("");

  const filtered = useMemo(
    () => clients.filter((c) => c.name.toLowerCase().includes(search.trim().toLowerCase())),
    [clients, search]
  );

  return (
    <Card title="Clients">
      <input
        type="search"
        placeholder="Search clients…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="mb-3 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white focus:border-accent focus:outline-none"
      />
      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {!isLoading && filtered.length === 0 && (
        <p className="text-sm text-slate-500">No clients found.</p>
      )}
      <div className="max-h-64 space-y-1 overflow-y-auto">
        {filtered.map((c) => (
          <Link
            key={c.id}
            to={`/clients/${c.id}/timeline`}
            className="flex items-center gap-2 justify-between rounded-lg px-2 py-1.5 text-sm text-slate-300 hover:bg-white/5"
          >
            <span className="flex items-center gap-2 min-w-0">
              <Avatar name={c.name} />
              <span className="truncate">{c.name}</span>
            </span>
            {c.pending_checkins_count > 0 && (
              <span className="shrink-0 rounded-full bg-amber-500/15 px-2 py-0.5 text-xs font-medium text-amber-400">
                {c.pending_checkins_count} pending
              </span>
            )}
          </Link>
        ))}
      </div>
    </Card>
  );
}

function PendingCheckinsWidget({
  items,
  isLoading,
}: {
  items: PendingCheckinSummary[];
  isLoading: boolean;
}) {
  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          Unseen check-ins
          {items.length > 0 && (
            <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1 text-xs font-semibold text-white">
              {items.length}
            </span>
          )}
        </span>
      }
    >
      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {!isLoading && items.length === 0 && (
        <p className="text-sm text-slate-500">No pending check-ins.</p>
      )}
      <div className="max-h-64 space-y-2 overflow-y-auto">
        {items.map((item) => (
          <Link
            key={item.id}
            to={`/clients/${item.client_id}/checkins`}
            className="flex items-center gap-2 rounded-lg bg-amber-500/5 px-3 py-2 hover:bg-amber-500/10"
          >
            <Avatar name={item.client_name} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm text-slate-200">{item.client_name}</p>
              <p className="text-xs text-slate-500">
                {new Date(item.submitted_at).toLocaleDateString("en-US")}
                {item.weight_kg != null ? ` · ${item.weight_kg} kg` : ""}
              </p>
            </div>
          </Link>
        ))}
      </div>
    </Card>
  );
}

function NeedsAttentionWidget({
  items,
  isLoading,
}: {
  items: NeedsAttentionClient[];
  isLoading: boolean;
}) {
  return (
    <Card title="Needs attention">
      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {!isLoading && items.length === 0 && (
        <p className="flex items-center gap-1.5 text-sm text-emerald-400">
          <span aria-hidden="true">✓</span> Everyone's on track — no client overdue.
        </p>
      )}
      <div className="max-h-64 space-y-1 overflow-y-auto">
        {items.map((entry) => (
          <Link
            key={entry.client_id}
            to={`/clients/${entry.client_id}/timeline`}
            className="flex items-center justify-between rounded-lg bg-red-500/5 px-3 py-2 text-sm hover:bg-red-500/10"
          >
            <span className="text-slate-200">{entry.client_name}</span>
            <span className="text-xs text-red-400">
              {entry.days_since_activity === null
                ? "Never active"
                : `${entry.days_since_activity} days quiet`}
            </span>
          </Link>
        ))}
      </div>
    </Card>
  );
}

function WeekStatsWidget({
  stats,
  activeClientsLast7Days,
  isLoading,
}: {
  stats: CoachDashboardSummary["week_stats"] | undefined;
  activeClientsLast7Days: number[];
  isLoading: boolean;
}) {
  return (
    <Card title="This week">
      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {!isLoading && stats && (
        <div className="grid grid-cols-3 gap-2">
          <div>
            <p className="text-xl font-medium text-accent">{stats.checkins}</p>
            <p className="text-xs text-slate-500">check-ins</p>
          </div>
          <div>
            <p className="text-xl font-medium text-accent">{stats.photos}</p>
            <p className="text-xs text-slate-500">photos</p>
          </div>
          <div>
            <p className="text-xl font-medium text-accent">{stats.active_clients}</p>
            <p className="text-xs text-slate-500">active clients</p>
            <div className="mt-1">
              <Sparkline values={activeClientsLast7Days} />
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}

function activityLabel(item: ActivityItem): string {
  switch (item.type) {
    case "checkin_submitted":
      return `${item.client_name} submitted a check-in`;
    case "checkin_reviewed":
      return `Feedback sent to ${item.client_name}`;
    case "client_added":
      return `${item.client_name} was added as a client`;
  }
}

function relativeTime(isoTimestamp: string): string {
  const diffMs = Date.now() - new Date(isoTimestamp).getTime();
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  if (diffHours < 1) return "just now";
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays === 1) return "yesterday";
  return `${diffDays}d ago`;
}

function ActivityFeedWidget({ items, isLoading }: { items: ActivityItem[]; isLoading: boolean }) {
  return (
    <Card title="Recent activity" className="md:col-span-2">
      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {!isLoading && items.length === 0 && (
        <p className="text-sm text-slate-500">Nothing yet — activity will show up here.</p>
      )}
      <div className="space-y-1">
        {items.map((item) => (
          <div
            key={`${item.type}-${item.client_id}-${item.timestamp}`}
            className="flex items-center gap-2 border-b border-white/5 py-1.5 last:border-0"
          >
            <Avatar name={item.client_name} />
            <p className="flex-1 text-sm text-slate-300">{activityLabel(item)}</p>
            <p className="shrink-0 text-xs text-slate-500">{relativeTime(item.timestamp)}</p>
          </div>
        ))}
      </div>
    </Card>
  );
}

function WeeklyCheckinsChartWidget({
  weeks,
  isLoading,
}: {
  weeks: { week_start: string; count: number }[];
  isLoading: boolean;
}) {
  const max = Math.max(1, ...weeks.map((w) => w.count));
  return (
    <Card title="Check-ins per week" className="md:col-span-2">
      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {!isLoading && weeks.length === 0 && (
        <p className="text-sm text-slate-500">No check-ins yet.</p>
      )}
      {!isLoading && weeks.length > 0 && (
        <div className="flex h-24 items-end gap-3">
          {weeks.map((w) => (
            <div key={w.week_start} className="flex flex-1 flex-col items-center gap-1">
              <div
                className="w-full rounded-t bg-accent/60"
                style={{ height: `${Math.max(4, (w.count / max) * 100)}%` }}
                title={`${w.count} check-ins`}
              />
              <p className="text-[10px] text-slate-500">
                {new Date(w.week_start).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
              </p>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
