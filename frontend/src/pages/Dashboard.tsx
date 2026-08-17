// frontend/src/pages/Dashboard.tsx
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import PageHeader from "../components/PageHeader";
import { EmptyState } from "../components/EmptyState";
import { UpgradeBanner } from "../components/UpgradeBanner";
import { useCurrentUser } from "../hooks/useCurrentUser";
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clients"] });
      setShowForm(false);
      setName("");
      setHeightCm("");
      setBirthDate("");
      setGender("");
      setStartDate("");
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
        title="Meine Kunden"
        actions={
          <button
            onClick={() => setShowForm((s) => !s)}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90"
          >
            Neuen Kunden anlegen
          </button>
        }
      />

      {user?.account_type === "coach" &&
        !["trialing", "active"].includes(user.subscription_status ?? "") &&
        clients.length >= 1 && (
          <UpgradeBanner message="Du nutzt bereits einen Klienten kostenlos — für weitere brauchst du ein Abo." />
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
            Körpergröße (cm)
            <input
              type="number"
              value={heightCm}
              onChange={(e) => setHeightCm(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Geburtsdatum
            <input
              type="date"
              value={birthDate}
              onChange={(e) => setBirthDate(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Geschlecht
            <input
              value={gender}
              onChange={(e) => setGender(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Startdatum
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          {(createMutation.error as any)?.response?.status === 402 && (
            <p className="text-sm text-red-400 sm:col-span-2">
              Klienten-Limit erreicht -{" "}
              <Link to="/account" className="underline">
                Abo abschließen/upgraden
              </Link>
              , um weitere Klienten anzulegen.
            </p>
          )}
          <div className="flex items-end">
            <button
              type="submit"
              disabled={!name.trim() || createMutation.isPending}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-40"
            >
              {createMutation.isPending ? "Anlegen…" : "Anlegen"}
            </button>
          </div>
        </form>
      )}

      {clients.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-3">
          <input
            type="search"
            placeholder="Kunde suchen…"
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
              <option value="">Alle Geschlechter</option>
              {availableGenders.map((g) => (
                <option key={g} value={g}>
                  {g}
                </option>
              ))}
            </select>
          )}
        </div>
      )}

      {clientsQuery.isLoading && <p className="text-slate-500">Lade…</p>}

      {!clientsQuery.isLoading && clients.length === 0 && (
        <EmptyState
          icon="🚀"
          title="Noch kein Klient an Bord"
          description="Leg deinen ersten Klienten an und starte den Check-in-Flow."
          action={
            <button
              onClick={() => setShowForm(true)}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90"
            >
              Ersten Klienten anlegen
            </button>
          }
        />
      )}

      {!clientsQuery.isLoading && clients.length > 0 && filteredClients.length === 0 && (
        <div className="rounded-xl border border-dashed border-white/10 p-8 text-center text-slate-500">
          Keine Kunden gefunden.
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
  const metaLine = [age ? `${age} Jahre` : null, c.height_cm ? `${c.height_cm} cm` : null]
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
            {c.pending_checkins_count} offene{c.pending_checkins_count === 1 ? "r" : ""} Check-in
            {c.pending_checkins_count === 1 ? "" : "s"}
          </span>
        )}
      </div>
      <p className="mt-1 text-xs text-slate-500">{metaLine || "Keine Metriken hinterlegt"}</p>
      <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
        <span>{c.photo_count} Fotos</span>
        <span>
          {c.last_activity
            ? `Zuletzt: ${new Date(c.last_activity).toLocaleDateString("de-DE")}`
            : "Keine Fotos"}
        </span>
      </div>
    </Link>
  );
}
