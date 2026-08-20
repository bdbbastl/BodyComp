// frontend/src/components/OnboardingEndModal.tsx
import { useOnboarding } from "../contexts/OnboardingContext";

/** Letzter Schritt der Coach-Tour - siehe Design-Spec "Coach-Onboarding-
 * Tour v2" Teil 3. Bietet an, den während der Tour angelegten Test-
 * Klienten wieder zu löschen, damit der Coach sauber mit einem echten
 * ersten Klienten starten kann. */
export function OnboardingEndModal() {
  const { phase, tourClientId, finishTour, deleteTourClient, isDeletingTourClient } = useOnboarding();

  if (phase !== "end") return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-md rounded-xl border border-white/10 bg-surface p-6 shadow-2xl">
        <p className="text-2xl">🎉</p>
        <h1 className="mt-2 text-xl font-semibold text-white">You're all set!</h1>
        <p className="mt-2 text-sm text-slate-400">
          {tourClientId !== null
            ? "Want to keep the client you just created, or delete it to start clean with your first real client?"
            : "You've seen everything - happy coaching!"}
        </p>
        <div className="mt-5 flex flex-wrap gap-2">
          <button
            onClick={finishTour}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90"
          >
            {tourClientId !== null ? "Keep this client" : "Close"}
          </button>
          {tourClientId !== null && (
            <button
              onClick={deleteTourClient}
              disabled={isDeletingTourClient}
              className="rounded-lg border border-red-900/50 px-4 py-2 text-sm text-red-400 hover:bg-red-950/30 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isDeletingTourClient ? "Deleting…" : "Delete this client"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
