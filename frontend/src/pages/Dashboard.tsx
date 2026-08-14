import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";

export default function Dashboard() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [heightCm, setHeightCm] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [gender, setGender] = useState("");
  const [startDate, setStartDate] = useState("");

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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-white">Meine Kunden</h1>
        <button
          onClick={() => setShowForm((s) => !s)}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90"
        >
          Neuen Kunden anlegen
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim()) createMutation.mutate();
          }}
          className="grid grid-cols-1 gap-3 rounded-xl border border-white/5 bg-surface p-4 sm:grid-cols-2"
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

      {clientsQuery.isLoading && <p className="text-slate-500">Lade…</p>}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {clients.map((c) => (
          <Link
            key={c.id}
            to={`/clients/${c.id}/timeline`}
            className="rounded-xl border border-white/5 bg-surface p-4 transition-colors hover:border-accent/40"
          >
            <p className="text-base font-semibold text-white">{c.name}</p>
            <p className="mt-1 text-xs text-slate-500">
              {[
                c.birth_date
                  ? `${Math.floor((Date.now() - new Date(c.birth_date).getTime()) / (365.25 * 24 * 60 * 60 * 1000))} Jahre`
                  : null,
                c.height_cm ? `${c.height_cm} cm` : null,
              ]
                .filter(Boolean)
                .join(" · ") || "Keine Metriken hinterlegt"}
            </p>
          </Link>
        ))}
      </div>
    </div>
  );
}
