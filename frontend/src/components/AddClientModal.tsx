// frontend/src/components/AddClientModal.tsx
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useOnboarding } from "../contexts/OnboardingContext";
import { useNavigate } from "react-router-dom";

/** Ersetzt das frühere Inline-Formular auf dem Dashboard - siehe
 * Design-Spec "Coach-Onboarding-Tour v2" Teil 5. Nur noch 3 Felder
 * (Name, Date of Birth, Gender) - Height und das ungenutzte Start Date
 * sind entfallen, Gewicht gibt es hier bewusst nicht (kommt erst mit
 * dem ersten Foto-Upload). */
export function AddClientModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [gender, setGender] = useState("");
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { phase, stepIndex, steps, nextStep, setTourClientId } = useOnboarding();

  const createMutation = useMutation({
    mutationFn: () =>
      api.clients.create({
        name,
        birth_date: birthDate.trim() === "" ? null : birthDate,
        gender: gender.trim() === "" ? null : gender,
      }),
    onSuccess: (createdClient) => {
      queryClient.invalidateQueries({ queryKey: ["clients"] });
      if (phase === "tour" && steps[stepIndex]?.id === "new-client") {
        setTourClientId(createdClient.id);
        nextStep();
        navigate(`/clients/${createdClient.id}/settings`);
        onClose();
      }
      // Außerhalb der Tour bleibt das Modal kurz mit einer Erfolgsmeldung
      // offen (siehe isSuccess-Zweig unten), statt sofort zu schließen.
    },
  });

  return (
    <div
      className="fixed inset-0 z-[90] flex items-center justify-center bg-black/70 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-sm rounded-xl border border-white/10 bg-surface p-6 shadow-2xl">
        <h2 className="mb-4 text-lg font-semibold text-white">Add New Client</h2>

        {createMutation.isSuccess ? (
          <div className="space-y-3">
            <p className="text-sm text-emerald-400">✓ Client added!</p>
            <button
              onClick={onClose}
              className="w-full rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90"
            >
              Close
            </button>
          </div>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (name.trim()) createMutation.mutate();
            }}
            className="space-y-3"
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
              <select
                value={gender}
                onChange={(e) => setGender(e.target.value)}
                className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
              >
                <option value="">Select…</option>
                <option value="Male">Male</option>
                <option value="Female">Female</option>
                <option value="Other">Other</option>
              </select>
            </label>

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={onClose}
                disabled={createMutation.isPending}
                className="rounded-lg border border-white/15 px-4 py-2 text-sm font-medium text-white hover:bg-white/5 disabled:opacity-40"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={!name.trim() || createMutation.isPending}
                className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-40"
              >
                {createMutation.isPending && (
                  <span className="h-3 w-3 animate-spin rounded-full border-2 border-slate-900 border-t-transparent" />
                )}
                {createMutation.isPending ? "Saving…" : "Save"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
