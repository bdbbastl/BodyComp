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
    id: "checkin-link",
    dataTour: "settings-checkin-link",
    title: "Share the check-in link",
    body: "Your client uses this link to submit check-ins - no account needed on their side.",
  },
  {
    id: "checkins-nav",
    dataTour: "nav-checkins",
    title: "Review check-ins",
    body: "Submitted check-ins and your feedback show up here.",
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
  phase: "modal" | "tour" | null;
  modalSlide: number;
  stepIndex: number;
  steps: TourStep[];
  start: () => void;
  nextModalSlide: () => void;
  startTour: () => void;
  nextStep: () => void;
  skip: () => void;
  restart: () => void;
}

const OnboardingContext = createContext<OnboardingContextValue | null>(null);

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const { data: user } = useCurrentUser();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const clientsQuery = useQuery({ queryKey: ["clients"], queryFn: api.clients.list });
  const [phase, setPhase] = useState<"modal" | "tour" | null>(null);
  const [modalSlide, setModalSlide] = useState(0);
  const [stepIndex, setStepIndex] = useState(0);

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
        setPhase(null);
        completeMutation.mutate();
        return i;
      }
      return next;
    });
  }, [steps.length, completeMutation]);

  const skip = useCallback(() => {
    setPhase(null);
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
    start,
    nextModalSlide,
    startTour,
    nextStep,
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
