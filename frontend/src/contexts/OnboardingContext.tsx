// frontend/src/contexts/OnboardingContext.tsx
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useCurrentUser } from "../hooks/useCurrentUser";

export interface TourStep {
  id: string;
  dataTour: string;
  title: string;
  body: string;
}

export const COACH_STEPS: TourStep[] = [
  {
    id: "new-client",
    dataTour: "dashboard-new-client",
    title: "Add your first client",
    body: "This is where you add a new client to start tracking their progress.",
  },
  {
    id: "client-settings",
    dataTour: "nav-settings",
    title: "Client settings",
    body: "Every client has their own settings page - profile info, check-in reminders, and the magic link (next step).",
  },
  {
    id: "magic-link",
    dataTour: "settings-checkin-link",
    title: "The magic link",
    body: "This link lets your client submit weight and progress photos without creating an account. Copy it and send it to them - it stays valid permanently, and you can regenerate it here if needed.",
  },
  {
    id: "add-pose",
    dataTour: "settings-add-pose",
    title: "Create a pose",
    body: "Poses are the angles you photograph (e.g. Front, Side, Back) - they're the fixed reference points for before/after comparisons.",
  },
  {
    id: "checkins-nav",
    dataTour: "nav-checkins",
    title: "Review check-ins",
    body: "Submitted check-ins show up here, waiting for your review.",
  },
  {
    id: "checkins-review",
    dataTour: "checkins-review-area",
    title: "Give feedback",
    body: "Open a check-in to write feedback text, add a Loom video link, and mark it as reviewed - your client gets notified by email.",
  },
];

export const SINGLE_STEPS: TourStep[] = [
  {
    id: "upload",
    dataTour: "unprocessed-upload",
    title: "Upload your first photos",
    body: "Start by uploading your first progress photos here.",
  },
  {
    id: "timeline-nav",
    dataTour: "nav-timeline",
    title: "Your timeline",
    body: "This is where your progress over time shows up.",
  },
  {
    id: "compare-nav",
    dataTour: "nav-compare",
    title: "Compare photos",
    body: "Once you have 2 check-ins, you can compare before/after here.",
  },
];

interface OnboardingContextValue {
  phase: "modal" | "tour" | "end" | null;
  modalSlide: number;
  stepIndex: number;
  steps: TourStep[];
  tourClientId: number | null;
  start: () => void;
  nextModalSlide: () => void;
  startTour: () => void;
  nextStep: () => void;
  setTourClientId: (id: number) => void;
  finishTour: () => void;
  deleteTourClient: () => void;
  isDeletingTourClient: boolean;
  tourClientDeleteFailed: boolean;
  skip: () => void;
  restart: () => void;
}

const OnboardingContext = createContext<OnboardingContextValue | null>(null);

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const { data: user } = useCurrentUser();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  // Nur laden, wenn wirklich gebraucht (Single-Account, eingeloggt) - sonst
  // würde diese Query auch auf öffentlichen Seiten (Login/Signup) unnötig
  // mit 401 + Default-Retries (3x mit Backoff) feuern, siehe Pattern in
  // AppShell.tsx's clientsListQuery/useCurrentUser.ts (gefunden im
  // finalen Review).
  const clientsQuery = useQuery({
    queryKey: ["clients"],
    queryFn: api.clients.list,
    enabled: user?.account_type === "single",
    retry: false,
  });
  const [phase, setPhase] = useState<"modal" | "tour" | "end" | null>(null);
  const [modalSlide, setModalSlide] = useState(0);
  const [stepIndex, setStepIndex] = useState(0);
  const [tourClientId, setTourClientIdState] = useState<number | null>(null);

  const steps = useMemo(
    () => (user?.account_type === "coach" ? COACH_STEPS : SINGLE_STEPS),
    [user?.account_type]
  );

  const completeMutation = useMutation({
    mutationFn: api.auth.completeOnboarding,
    onSuccess: (data) => queryClient.setQueryData(["auth", "me"], data),
  });

  const start = useCallback(() => {
    setPhase("modal");
    setModalSlide(0);
    setStepIndex(0);
  }, []);

  const nextModalSlide = useCallback(() => {
    setModalSlide((s) => s + 1);
  }, []);

  const startTour = useCallback(() => {
    setPhase("tour");
    setStepIndex(0);
    if (user?.account_type === "coach") {
      navigate("/dashboard");
    } else {
      const firstClient = clientsQuery.data?.[0];
      if (firstClient) {
        navigate(`/clients/${firstClient.id}/unprocessed`);
      }
    }
  }, [navigate, user?.account_type, clientsQuery.data]);

  const nextStep = useCallback(() => {
    setStepIndex((i) => {
      const next = i + 1;
      if (next >= steps.length) {
        setPhase("end");
        return i;
      }
      return next;
    });
  }, [steps.length]);

  const setTourClientId = useCallback((id: number) => {
    setTourClientIdState(id);
  }, []);

  const finishTour = useCallback(() => {
    setPhase(null);
    setTourClientIdState(null);
    completeMutation.mutate();
  }, [completeMutation]);

  const deleteClientMutation = useMutation({
    mutationFn: (clientId: number) => api.clients.delete(clientId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clients"] });
      finishTour();
    },
    // Bewusst KEIN automatisches finishTour() bei Fehler - der Coach soll
    // sehen, dass das Löschen fehlgeschlagen ist, statt anzunehmen, es
    // hätte geklappt (siehe Design-Spec "Coach-Onboarding-Tour v2" Teil 3,
    // Review-Fund). "Keep this client" im OnboardingEndModal bleibt als
    // Ausweg jederzeit klickbar.
  });

  const deleteTourClient = useCallback(() => {
    if (tourClientId !== null) {
      deleteClientMutation.mutate(tourClientId);
    } else {
      finishTour();
    }
  }, [tourClientId, deleteClientMutation, finishTour]);

  const skip = useCallback(() => {
    setPhase(null);
    setTourClientIdState(null);
    completeMutation.mutate();
  }, [completeMutation]);

  const restart = useCallback(() => {
    start();
  }, [start]);

  const value: OnboardingContextValue = {
    phase,
    modalSlide,
    stepIndex,
    steps,
    tourClientId,
    start,
    nextModalSlide,
    startTour,
    nextStep,
    setTourClientId,
    finishTour,
    deleteTourClient,
    isDeletingTourClient: deleteClientMutation.isPending,
    tourClientDeleteFailed: deleteClientMutation.isError,
    skip,
    restart,
  };

  return <OnboardingContext.Provider value={value}>{children}</OnboardingContext.Provider>;
}

export function useOnboarding() {
  const ctx = useContext(OnboardingContext);
  if (!ctx) throw new Error("useOnboarding must be used within OnboardingProvider");
  return ctx;
}
