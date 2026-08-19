// frontend/src/contexts/BusyOverlayContext.tsx
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

interface BusyOverlayState {
  active: boolean;
  label: string;
  progressPercent: number | null; // null = kein Fortschrittsbalken, nur Spinner+Label
}

interface BusyOverlayActions {
  show: (label: string, progressPercent?: number | null) => void;
  updateProgress: (progressPercent: number) => void;
  hide: () => void;
}

// Zwei getrennte Contexts statt einem gemeinsamen: die Actions (show/hide/
// updateProgress) sind über useCallback referenzstabil und ändern nie ihre
// Identität, der State (active/label/progressPercent) ändert sich dagegen
// bei jedem show()/hide(). Ein einzelner kombinierter Context-Wert (früher:
// {...state, show, updateProgress, hide}) bekäme dadurch bei JEDEM
// State-Wechsel eine neue Objekt-Identität - jede Komponente, die
// useBusyOverlay() nur für die Actions aufruft (z.B. Timeline.tsx's
// PhotoCard, potenziell viele Instanzen auf einer Seite), würde dadurch bei
// JEDEM Show/Hide irgendwo in der App neu rendern, nicht nur bei einer
// tatsächlich für sie relevanten Änderung. Mit getrennten Contexts bleibt
// der Actions-Context stabil, nur BusyOverlay.tsx selbst konsumiert den
// State-Context und rendert bei Änderungen neu (was dort auch der einzige
// Zweck ist).
const BusyOverlayStateContext = createContext<BusyOverlayState | null>(null);
const BusyOverlayActionsContext = createContext<BusyOverlayActions | null>(null);

/** App-weites blockierendes Overlay fuer laengere Aktionen (Upload,
 * Bulk-Save) - siehe Design-Spec "Usability-Fixes Runde 2" Abschnitt 3+4.
 * Bewusst KEIN Abbrechen-Button (siehe Design-Entscheidung). */
export function BusyOverlayProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<BusyOverlayState>({
    active: false,
    label: "",
    progressPercent: null,
  });

  const show = useCallback((label: string, progressPercent: number | null = null) => {
    setState({ active: true, label, progressPercent });
  }, []);

  const updateProgress = useCallback((progressPercent: number) => {
    setState((s) => ({ ...s, progressPercent }));
  }, []);

  const hide = useCallback(() => {
    setState({ active: false, label: "", progressPercent: null });
  }, []);

  // useCallback allein reicht nicht, um die Objekt-IDENTITÄT von
  // {show, updateProgress, hide} stabil zu halten - ohne useMemo würde bei
  // jedem Provider-Rerender (z.B. durch den State-Wechsel oben) trotzdem
  // ein neues Objekt entstehen, auch wenn alle drei Funktionen selbst
  // referenzstabil sind.
  const actions = useMemo<BusyOverlayActions>(
    () => ({ show, updateProgress, hide }),
    [show, updateProgress, hide]
  );

  return (
    <BusyOverlayActionsContext.Provider value={actions}>
      <BusyOverlayStateContext.Provider value={state}>{children}</BusyOverlayStateContext.Provider>
    </BusyOverlayActionsContext.Provider>
  );
}

/** Für Komponenten, die nur show()/hide()/updateProgress() auslösen wollen
 * (der ganz überwiegende Fall) - liest NICHT den aktuellen active/label/
 * progressPercent-Zustand, rendert also nie neu, wenn sich der nur an
 * anderer Stelle in der App ändert. */
export function useBusyOverlay(): BusyOverlayActions {
  const ctx = useContext(BusyOverlayActionsContext);
  if (!ctx) throw new Error("useBusyOverlay must be used within BusyOverlayProvider");
  return ctx;
}

/** Nur für BusyOverlay.tsx selbst - liest den tatsächlichen Anzeige-Zustand. */
export function useBusyOverlayState(): BusyOverlayState {
  const ctx = useContext(BusyOverlayStateContext);
  if (!ctx) throw new Error("useBusyOverlayState must be used within BusyOverlayProvider");
  return ctx;
}
