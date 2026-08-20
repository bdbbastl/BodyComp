// frontend/src/components/OnboardingModal.tsx
import { useOnboarding } from "../contexts/OnboardingContext";
import { useCurrentUser } from "../hooks/useCurrentUser";

/** Zwei-Slide-Willkommens-Modal, das vor der Tooltip-Tour gezeigt wird -
 * siehe Design-Spec "Onboarding-Flow" Abschnitt 3. Fade-Transition
 * zwischen den Slides über eine simple key-basierte Remount-Animation
 * (Tailwind `animate-fade-in` via arbitrary keyframes wäre Overkill hier -
 * ein einfacher CSS transition auf opacity reicht). */
export function OnboardingModal() {
  const { modalSlide, nextModalSlide, startTour, skip } = useOnboarding();
  const { data: user } = useCurrentUser();
  const isCoach = user?.account_type === "coach";

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-4">
      <div className="relative w-full max-w-md rounded-xl border border-white/10 bg-surface p-6 shadow-2xl transition-all duration-300">
        <button
          onClick={skip}
          className="absolute right-4 top-4 text-xs text-slate-500 hover:text-white"
        >
          Skip
        </button>

        {modalSlide === 0 && (
          <div className="animate-[fadeIn_0.3s_ease-out] space-y-3">
            <p className="text-2xl">👋</p>
            <h1 className="text-xl font-semibold text-white">Welcome to BodyComp Tracker</h1>
            <p className="text-sm text-slate-400">
              {isCoach
                ? "Let's get you set up to track your clients' progress."
                : "Let's get you set up to track your own progress."}
            </p>
            <button
              onClick={nextModalSlide}
              className="mt-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90"
            >
              Next
            </button>
          </div>
        )}

        {modalSlide === 1 && (
          <div className="animate-[fadeIn_0.3s_ease-out] space-y-3">
            <h2 className="text-lg font-semibold text-white">Here's what we'll show you</h2>
            <ul className="space-y-1.5 text-sm text-slate-300">
              {isCoach ? (
                <>
                  <li>1. Adding your first client</li>
                  <li>2. Client settings & the magic link</li>
                  <li>3. Creating poses</li>
                  <li>4. Reviewing check-ins & giving feedback</li>
                </>
              ) : (
                <>
                  <li>1. Uploading your first photos</li>
                  <li>2. Your timeline</li>
                  <li>3. Comparing progress photos</li>
                </>
              )}
            </ul>
            <button
              onClick={startTour}
              className="mt-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90"
            >
              Let's go
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
