// frontend/src/components/ClientShell.tsx
import { useEffect, useState } from "react";
import { NavLink, Outlet, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

const SIDEBAR_COLLAPSED_KEY = "bodycomp:sidebarCollapsed";

const NAV_ITEMS = [
  { to: "timeline", label: "Timeline", icon: "📅" },
  { to: "unprocessed", label: "Import", icon: "📥" },
  { to: "compare", label: "Compare", icon: "🔍" },
  { to: "statistics", label: "Statistik", icon: "📊" },
  { to: "settings", label: "Settings", icon: "⚙️" },
];

/** Nur aktiv innerhalb /clients/:clientId/* - fügt die vertikale
 * Kunden-Navi + Mini-Header (aktueller Kundenname) hinzu, siehe
 * Design-Spec Abschnitt "ClientShell (vertikale Kunden-Navi)". */
export default function ClientShell() {
  const { clientId } = useParams<{ clientId: string }>();
  const [desktopCollapsed, setDesktopCollapsed] = useState(() => {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true";
  });
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(desktopCollapsed));
  }, [desktopCollapsed]);

  const clientQuery = useQuery({
    queryKey: ["clients", clientId],
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
        aria-label="Navigation öffnen"
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
                end={item.to === "timeline"}
                onClick={() => setMobileOpen(false)}
                className={navLinkClass}
              >
                <span>{item.icon}</span>
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      )}

      {/* Desktop: feste Sidebar, einklappbar */}
      <nav
        className={`hidden shrink-0 flex-col gap-1 sm:flex ${
          desktopCollapsed ? "w-12" : "w-48"
        } transition-all`}
      >
        <button
          onClick={() => setDesktopCollapsed((c) => !c)}
          className="mb-2 self-end rounded-lg p-2 text-slate-500 hover:bg-white/5 hover:text-white"
          aria-label={desktopCollapsed ? "Navigation ausklappen" : "Navigation einklappen"}
        >
          {desktopCollapsed ? "»" : "«"}
        </button>
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "timeline"}
            className={navLinkClass}
            title={desktopCollapsed ? item.label : undefined}
          >
            <span>{item.icon}</span>
            {!desktopCollapsed && item.label}
          </NavLink>
        ))}
      </nav>

      <div className="min-w-0 flex-1">
        {clientQuery.data && (
          <div className="mb-4 flex items-center gap-2 rounded-lg bg-surface/60 px-3 py-1.5 text-sm text-slate-300">
            <span className="text-slate-500">Kunde:</span> {clientQuery.data.name}
          </div>
        )}
        <Outlet />
      </div>
    </div>
  );
}
