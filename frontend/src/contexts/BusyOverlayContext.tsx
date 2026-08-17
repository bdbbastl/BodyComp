// frontend/src/contexts/BusyOverlayContext.tsx
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

interface BusyOverlayState {
  active: boolean;
  label: string;
  progressPercent: number | null; // null = kein Fortschrittsbalken, nur Spinner+Label
}

interface BusyOverlayContextValue extends BusyOverlayState {
  show: (label: string, progressPercent?: number | null) => void;
  updateProgress: (progressPercent: number) => void;
  hide: () => void;
}

const BusyOverlayContext = createContext<BusyOverlayContextValue | null>(null);

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

  return (
    <BusyOverlayContext.Provider value={{ ...state, show, updateProgress, hide }}>
      {children}
    </BusyOverlayContext.Provider>
  );
}

export function useBusyOverlay() {
  const ctx = useContext(BusyOverlayContext);
  if (!ctx) throw new Error("useBusyOverlay must be used within BusyOverlayProvider");
  return ctx;
}
