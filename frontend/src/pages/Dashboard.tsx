// frontend/src/pages/Dashboard.tsx
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import PageHeader from "../components/PageHeader";
import { EmptyState } from "../components/EmptyState";
import { SkeletonGrid } from "../components/Skeleton";
import { UpgradeBanner } from "../components/UpgradeBanner";
import { useCurrentUser } from "../hooks/useCurrentUser";
import { useOnboarding } from "../contexts/OnboardingContext";
import type { Client } from "../types";

function ageFromBirthDate(birthDate: string | null): number | null {
  if (!birthDate) return null;
  return Math.floor(
    (Date.now() - new Date(birthDate).getTime()) / (365.25 * 24 * 60 * 60 * 1000)
  );
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

  const [search, setSearch] = useState("");
  const [genderFilter, setGenderFilter] = useState("");

  const clientsQuery = useQuery({ queryKey: ["clients"], queryFn: api.clients.list });

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

  const availableGenders = useMemo(
    () => Array.from(new Set(clients.map((c) => c.gender).filter((g): g is string => !!g))),
    [clients]
  );

  const filteredClients = useMemo(() => {
    return clients.filter((c) => {
      const matchesSearch = c.name.toLowerCase().includes(search.trim().toLowerCase());
      const matchesGender = !genderFilter || c.gender === genderFilter;
      return matchesSearch && matchesGender;
    });
  }, [clients, search, genderFilter]);

  return (
    <div>
      <PageHeader
        title="My Clients"
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

      {clients.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-3">
          <input
            type="search"
            placeholder="Search clients…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="min-w-[200px] flex-1 rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white focus:border-accent focus:outline-none"
          />
          {availableGenders.length > 0 && (
            <select
              value={genderFilter}
              onChange={(e) => setGenderFilter(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white focus:border-accent focus:outline-none"
            >
              <option value="">All Genders</option>
              {availableGenders.map((g) => (
                <option key={g} value={g}>
                  {g}
                </option>
              ))}
            </select>
          )}
        </div>
      )}

      {clientsQuery.isLoading && <SkeletonGrid />}

      {!clientsQuery.isLoading && clients.length === 0 && (
        <EmptyState
          icon="🚀"
          title="No clients on board yet"
          description="Add your first client and start the check-in flow."
          action={
            <button
              onClick={() => setShowForm(true)}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90"
            >
              Add First Client
            </button>
          }
        />
      )}

      {!clientsQuery.isLoading && clients.length > 0 && filteredClients.length === 0 && (
        <div className="rounded-xl border border-dashed border-white/10 p-8 text-center text-slate-500">
          No clients found.
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {filteredClients.map((c) => (
          <DashboardClientCard key={c.id} client={c} />
        ))}
      </div>
    </div>
  );
}

function DashboardClientCard({ client: c }: { client: Client }) {
  const age = ageFromBirthDate(c.birth_date);
  const metaLine = [age ? `${age} years` : null, c.height_cm ? `${c.height_cm} cm` : null]
    .filter(Boolean)
    .join(" · ");

  return (
    <Link
      to={`/clients/${c.id}/timeline`}
      className="rounded-xl border border-white/5 bg-surface p-4 transition-colors hover:border-accent/40"
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-base font-semibold text-white">{c.name}</p>
        {c.pending_checkins_count > 0 && (
          <span className="shrink-0 rounded-full bg-amber-500/15 px-2 py-0.5 text-xs font-medium text-amber-400">
            {c.pending_checkins_count} pending check-in
            {c.pending_checkins_count === 1 ? "" : "s"}
          </span>
        )}
      </div>
      <p className="mt-1 text-xs text-slate-500">{metaLine || "No metrics on file"}</p>
      <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
        <span>{c.photo_count} photos</span>
        <span>
          {c.last_activity
            ? `Last: ${new Date(c.last_activity).toLocaleDateString("en-US")}`
            : "No photos"}
        </span>
      </div>
    </Link>
  );
}
