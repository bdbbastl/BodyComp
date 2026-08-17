// frontend/src/components/ClientShell.tsx
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

const SIDEBAR_COLLAPSED_KEY = "bodycomp:sidebarCollapsed";

const NAV_ITEMS = [
  { to: "timeline", label: "Timeline", icon: "📅" },
  { to: "checkins", label: "Check-ins", icon: "✅" },
  { to: "unprocessed", label: "Import", icon: "📥" },
  { to: "compare", label: "Compare", icon: "🔍" },
  { to: "statistics", label: "Statistics", icon: "📊" },
  { to: "settings", label: "Settings", icon: "⚙️" },
];

/** Nur aktiv innerhalb /clients/:clientId/* - fügt die vertikale
 * Kunden-Navi + Mini-Header (aktueller Kundenname) hinzu, siehe
 * Design-Spec Abschnitt "ClientShell (vertikale Kunden-Navi)". */
export default function ClientShell() {
  const { clientId } = useParams<{ clientId: string }>();
  const location = useLocation();
  const activeNavTo = NAV_ITEMS.find((item) =>
    item.to === "timeline"
      ? location.pathname.endsWith(`/clients/${clientId}/timeline`)
      : location.pathname.includes(`/clients/${clientId}/${item.to}`)
  )?.to;
  const [desktopCollapsed, setDesktopCollapsed] = useState(() => {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true";
  });
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(desktopCollapsed));
  }, [desktopCollapsed]);

  const clientQuery = useQuery({
    // Numerisch, wie in Settings.tsx/ClientCheckins.tsx - sonst sind
    // ["clients", "5"] (string) und ["clients", 5] (number) für React
    // Query zwei getrennte Cache-Einträge, und ein invalidateQueries aus
    // Settings.tsx würde diesen Query hier nie treffen (gefunden im
    // Review von Task 15).
    queryKey: ["clients", Number(clientId)],
    queryFn: () => api.clients.get(Number(clientId)),
    enabled: !!clientId,
  });

  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
      isActive ? "bg-accent text-slate-900" : "text-slate-400 hover:bg-white/5 hover:text-white"
    }`;

  return (
    <div className="flex gap-6">
      {/* Mobile: schmale Leiste mit Toggle, Overlay beim Ausklappen */}
      <button
        onClick={() => setMobileOpen(true)}
        className="fixed left-0 top-16 z-20 rounded-r-lg border border-l-0 border-white/10 bg-surface px-2 py-3 text-slate-400 sm:hidden"
        aria-label="Open navigation"
      >
        ☰
      </button>
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 sm:hidden"
          onClick={() => setMobileOpen(false)}
        >
          <nav
            className="flex h-full w-56 flex-col gap-1 bg-surface p-4"
            onClick={(e) => e.stopPropagation()}
          >
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                data-tour={`nav-${item.to}`}
                end={item.to === "timeline"}
                aria-disabled={item.to === activeNavTo}
                onClick={(e) => {
                  if (item.to === activeNavTo) {
                    e.preventDefault();
                    return;
                  }
                  setMobileOpen(false);
                }}
                className={navLinkClass}
              >
                <span>{item.icon}</span>
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      )}

      {/* Desktop: feste Sidebar, einklappbar - Container fasst die Punkte
          visuell zusammen (siehe Design-Spec "UX-Politur" Abschnitt 1),
          Toggle steht unten, abgesetzt durch einen Trennstrich, statt
          isoliert oben zu "hängen". */}
      <nav
        className={`hidden shrink-0 flex-col gap-1 rounded-xl bg-surface/40 p-2 sm:flex ${
          desktopCollapsed ? "w-14" : "w-48"
        } transition-all`}
      >
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            data-tour={`nav-${item.to}`}
            end={item.to === "timeline"}
            aria-disabled={item.to === activeNavTo}
            onClick={(e) => item.to === activeNavTo && e.preventDefault()}
            className={navLinkClass}
            title={desktopCollapsed ? item.label : undefined}
          >
            <span>{item.icon}</span>
            {!desktopCollapsed && item.label}
          </NavLink>
        ))}
        <div className="mt-1 border-t border-white/10 pt-1">
          <button
            onClick={() => setDesktopCollapsed((c) => !c)}
            className="flex w-full items-center justify-center rounded-lg p-2 text-slate-500 hover:bg-white/5 hover:text-white"
            aria-label={desktopCollapsed ? "Expand navigation" : "Collapse navigation"}
          >
            {desktopCollapsed ? "»" : "«"}
          </button>
        </div>
      </nav>

      <div className="min-w-0 flex-1">
        {clientQuery.data && (
          <div className="mb-4 flex items-center gap-2 rounded-lg bg-surface/60 px-3 py-1.5 text-sm text-slate-300">
            <span className="text-slate-500">Client:</span> {clientQuery.data.name}
          </div>
        )}
        <Outlet />
      </div>
    </div>
  );
}
