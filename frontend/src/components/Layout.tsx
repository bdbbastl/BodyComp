import { NavLink, Outlet, useParams } from "react-router-dom";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useCurrentUser } from "../hooks/useCurrentUser";

export default function Layout() {
  const { clientId } = useParams<{ clientId: string }>();
  const { data: user } = useCurrentUser();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const clientQuery = useQuery({
    queryKey: ["clients", clientId],
    queryFn: () => api.clients.get(Number(clientId)),
    enabled: !!clientId,
  });

  // Für single-Accounts: der eine Client, zu dem man zurückkehren kann,
  // wenn man sich gerade NICHT in einer Client-Route befindet (z.B. auf
  // /account) - sonst gibt es für single-Accounts von dort keinen Weg
  // zurück, da sie kein Dashboard haben.
  const clientsListQuery = useQuery({
    queryKey: ["clients"],
    queryFn: api.clients.list,
    enabled: !clientId && user?.account_type === "single",
  });

  const logoutMutation = useMutation({
    mutationFn: api.auth.logout,
    onSuccess: () => {
      queryClient.clear();
      navigate("/login");
    },
  });

  const navItems = clientId
    ? [
        { to: `/clients/${clientId}/timeline`, label: "Timeline", end: true },
        { to: `/clients/${clientId}/unprocessed`, label: "Import" },
        { to: `/clients/${clientId}/compare`, label: "Compare" },
        { to: `/clients/${clientId}/statistics`, label: "Statistik" },
        { to: `/clients/${clientId}/settings`, label: "Settings" },
      ]
    : [];

  return (
    <div className="min-h-screen bg-background text-slate-100">
      <header className="sticky top-0 z-20 border-b border-white/5 bg-background/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold tracking-wide text-white">
              BodyComp <span className="text-accent">Tracker</span>
            </span>
            {user?.account_type === "coach" && (
              <>
                <span className="text-slate-600">·</span>
                <NavLink to="/dashboard" className="text-xs text-slate-400 hover:text-white">
                  ← Dashboard
                </NavLink>
                {clientQuery.data && (
                  <span className="text-sm text-slate-300">{clientQuery.data.name}</span>
                )}
              </>
            )}
            {user?.account_type === "single" && !clientId && clientsListQuery.data?.[0] && (
              <>
                <span className="text-slate-600">·</span>
                <NavLink
                  to={`/clients/${clientsListQuery.data[0].id}/timeline`}
                  className="text-xs text-slate-400 hover:text-white"
                >
                  ← Zurück zu {clientsListQuery.data[0].name}
                </NavLink>
              </>
            )}
          </div>
          <div className="flex items-center gap-3">
            <nav className="flex gap-1 rounded-full bg-surface p-1">
              {navItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    `rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
                      isActive
                        ? "bg-accent text-slate-900"
                        : "text-slate-400 hover:text-white"
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
            <NavLink to="/account" className="text-xs text-slate-400 hover:text-white">
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
      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
        <Outlet />
      </main>
    </div>
  );
}
