import { useEffect } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useCurrentUser } from "../hooks/useCurrentUser";
import { UpgradeBanner } from "./UpgradeBanner";
import { useOnboarding } from "../contexts/OnboardingContext";

/** Äußerer Rahmen, identisch auf JEDER eingeloggten Seite - siehe
 * Design-Spec Abschnitt "AppShell (oberer Header)". Enthält keine
 * kunden-spezifische Navigation mehr - das übernimmt ClientShell für
 * /clients/:id/*-Routen (siehe components/ClientShell.tsx). */
export default function AppShell() {
  const { data: user } = useCurrentUser();
  const { start } = useOnboarding();
  useEffect(() => {
    if (user && user.onboarding_completed_at === null) {
      start();
    }
    // Bewusst nur user?.id als Dependency (nicht das ganze user-Objekt) -
    // sonst würde dieser Effect erneut feuern, sobald sich
    // onboarding_completed_at nach Tour-Abschluss ändert, und die Tour
    // ungewollt erneut auslösen.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();

  const logoutMutation = useMutation({
    mutationFn: api.auth.logout,
    onSuccess: () => {
      queryClient.clear();
      // Zur Landing-Page statt Login - Login wirkt nach dem Ausloggen wie
      // ein Sackgassen-Fehlerbildschirm, Landing gibt dem User wieder
      // Kontext (und einen Weg zurück zum Login, falls gewünscht).
      navigate("/");
    },
  });

  const onDashboard = location.pathname === "/dashboard";
  const inClientRoute = location.pathname.startsWith("/clients/");

  // Für single-Accounts: der eine Client, zu dem man zurückkehren kann,
  // wenn man sich gerade NICHT in einer Client-Route befindet (z.B. auf
  // /account) - sonst gibt es für single-Accounts von dort keinen Weg
  // zurück, da sie kein Dashboard haben.
  const clientsListQuery = useQuery({
    queryKey: ["clients"],
    queryFn: api.clients.list,
    enabled: !inClientRoute && user?.account_type === "single",
  });
  const backToClient = clientsListQuery.data?.[0];

  return (
    <div className="min-h-screen bg-background text-slate-100">
      <header className="sticky top-0 z-30 border-b border-white/5 bg-background/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <Link
              to={user?.account_type === "coach" ? "/dashboard" : "/app"}
              className="text-sm font-semibold tracking-wide text-white transition-colors hover:text-accent"
            >
              BodyComp <span className="text-accent">Tracker</span>
            </Link>
            {user?.account_type === "coach" && (
              <NavLink
                to="/dashboard"
                aria-disabled={onDashboard}
                onClick={(e) => onDashboard && e.preventDefault()}
                className={`text-xs ${
                  onDashboard
                    ? "cursor-default font-medium text-accent"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                Dashboard
              </NavLink>
            )}
            {user?.account_type === "single" && !inClientRoute && backToClient && (
              <NavLink
                to={`/clients/${backToClient.id}/timeline`}
                className="text-xs text-slate-400 hover:text-white"
              >
                ← Back to {backToClient.name}
              </NavLink>
            )}
          </div>
          <div className="flex items-center gap-3">
            <NavLink
              to="/account"
              className={({ isActive }) =>
                `text-xs ${isActive ? "font-medium text-accent" : "text-slate-400 hover:text-white"}`
              }
            >
              Account
            </NavLink>
            <button
              onClick={() => logoutMutation.mutate()}
              className="text-xs text-slate-400 hover:text-white"
            >
              Logout
            </button>
          </div>
        </div>
      </header>
      {user?.subscription_status === "trialing" && user.trial_ends_at && (() => {
        const daysLeft = Math.max(
          0,
          Math.ceil((new Date(user.trial_ends_at).getTime() - Date.now()) / (1000 * 60 * 60 * 24))
        );
        return (
          <UpgradeBanner
            message={`${daysLeft} ${daysLeft === 1 ? "day" : "days"} left in your trial — lock in your plan now?`}
          />
        );
      })()}
      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
        <Outlet />
      </main>
    </div>
  );
}
