// frontend/src/components/OnboardingTooltip.tsx
import { useEffect, useState } from "react";
import { useOnboarding } from "../contexts/OnboardingContext";

/** Zeigt einen abgedunkelten Hintergrund mit "Spotlight"-Loch um das
 * Ziel-Element (per box-shadow-Trick, keine Library) + eine Sprechblase
 * daneben - siehe Design-Spec "Onboarding-Flow" Abschnitt 3+5. Pollt kurz,
 * bis das Ziel-Element im DOM auftaucht (z.B. nach dem Anlegen eines
 * Klienten). */
export function OnboardingTooltip() {
  const { phase, stepIndex, steps, nextStep, skip } = useOnboarding();
  const [rect, setRect] = useState<DOMRect | null>(null);

  const step = steps[stepIndex];
  const isLastStep = stepIndex === steps.length - 1;

  useEffect(() => {
    if (phase !== "tour" || !step) return;

    let cancelled = false;
    let attempts = 0;
    const poll = () => {
      if (cancelled) return;
      const el = document.querySelector(`[data-tour="${step.dataTour}"]`);
      if (el) {
        setRect(el.getBoundingClientRect());
        return;
      }
      attempts += 1;
      if (attempts < 40) {
        // ~4s Timeout (40 x 100ms) - danach bleibt die Sprechblase
        // ausgeblendet statt endlos zu pollen (z.B. wenn ein Coach-Account
        // Schritt 2 erreicht, ohne vorher wirklich einen Klienten angelegt
        // zu haben, siehe Design-Spec Abschnitt 4 "pausiert").
        setTimeout(poll, 100);
      }
    };
    setRect(null);
    poll();

    return () => {
      cancelled = true;
    };
  }, [phase, step]);

  if (phase !== "tour" || !step) return null;

  return (
    <div className="fixed inset-0 z-[100]">
      {rect && (
        <>
          {/* Spotlight: ein transparentes Rechteck exakt über dem Ziel-
              Element, mit einem riesigen box-shadow, der den Rest des
              Viewports abdunkelt - kein SVG-Masking o.ä. nötig. */}
          <div
            className="pointer-events-none fixed rounded-lg transition-all duration-300"
            style={{
              top: rect.top - 6,
              left: rect.left - 6,
              width: rect.width + 12,
              height: rect.height + 12,
              boxShadow: "0 0 0 9999px rgba(0,0,0,0.7)",
            }}
          />
          <div
            className="fixed z-[101] w-72 rounded-xl border border-accent/30 bg-surface p-4 shadow-2xl transition-all duration-300"
            style={{
              top: rect.bottom + 12,
              left: Math.min(rect.left, window.innerWidth - 300),
            }}
          >
            <p className="mb-1 text-sm font-semibold text-white">{step.title}</p>
            <p className="mb-3 text-xs text-slate-400">{step.body}</p>
            <div className="flex items-center justify-between">
              <button onClick={skip} className="text-xs text-slate-500 hover:text-white">
                Skip tour
              </button>
              <button
                onClick={nextStep}
                className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-slate-900 hover:opacity-90"
              >
                {isLastStep ? "Done" : "Next"}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
