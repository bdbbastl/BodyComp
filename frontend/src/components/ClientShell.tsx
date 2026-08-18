// frontend/src/components/ClientShell.tsx
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Menu,
  Calendar,
  ListChecks,
  Upload,
  GitCompare,
  BarChart3,
  Settings,
  type LucideIcon,
} from "lucide-react";
import { api } from "../api/client";
import { useCurrentUser } from "../hooks/useCurrentUser";

const SIDEBAR_COLLAPSED_KEY = "bodycomp:sidebarCollapsed";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  // Trennt diesen Punkt optisch von den vorherigen Punkten durch einen
  // Trennstrich - siehe Design-Spec "Sidebar-Redesign" Abschnitt
  // "Gruppierung". Erster Punkt jeder Gruppe außer der allerersten
  // bekommt startsNewGroup=true.
  startsNewGroup?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: "timeline", label: "Timeline", icon: Calendar },
  { to: "checkins", label: "Check-ins", icon: ListChecks },
  { to: "unprocessed", label: "Import", icon: Upload },
  { to: "compare", label: "Compare", icon: GitCompare, startsNewGroup: true },
  { to: "statistics", label: "Statistics", icon: BarChart3 },
  { to: "settings", label: "Settings", icon: Settings, startsNewGroup: true },
];

/** Nur aktiv innerhalb /clients/:clientId/* - fügt die vertikale
 * Kunden-Navi + Mini-Header (aktueller Kundenname) hinzu, siehe
 * Design-Spec Abschnitt "ClientShell (vertikale Kunden-Navi)" und
 * "Sidebar-Redesign" für die visuelle Aufbereitung (Icons, Gruppierung,
 * Toggle-Kopfzeile). */
export default function ClientShell() {
  const { clientId } = useParams<{ clientId: string }>();
  const { data: user } = useCurrentUser();
  // Check-ins ist eine Coach<->Klient-Beziehungsfunktion - bei Single-
  // Accounts (die sich selbst tracken) ergibt der Tab keinen Sinn, siehe
  // Design-Spec "Usability-Fixes Runde 2" Abschnitt 1. Reine
  // Sichtbarkeits-Filterung, keine Datenlöschung - wechselt ein Account
  // später zum Coach, taucht der Tab sofort wieder auf.
  const visibleNavItems = NAV_ITEMS.filter(
    (item) => item.to !== "checkins" || user?.account_type === "coach"
  );
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

  // Aktiver Zustand: 2px Cyan-Balken links + transparenter Cyan-Wash,
  // rechts abgerundet. Inaktiv: transparenter (aber reservierter) Balken,
  // damit beim Zustandswechsel nichts springt - siehe Design-Spec
  // "Sidebar-Redesign" Abschnitt "Aktiver Zustand".
  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-2 rounded-r-lg border-l-2 px-3 py-2 text-sm font-medium transition-colors ${
      isActive
        ? "border-accent bg-accent/10 text-accent"
        : "border-transparent text-slate-400 hover:text-white"
    }`;

  const renderNavItem = (item: NavItem, options: { collapsed?: boolean; onNavigate?: () => void } = {}) => {
    const Icon = item.icon;
    return (
      <div key={item.to}>
        {item.startsNewGroup && (
          <div className="my-1.5 border-t border-white/10" />
        )}
        <NavLink
          to={item.to}
          data-tour={`nav-${item.to}`}
          end={item.to === "timeline"}
          aria-disabled={item.to === activeNavTo}
          onClick={(e) => {
            if (item.to === activeNavTo) {
              e.preventDefault();
              return;
            }
            options.onNavigate?.();
          }}
          className={navLinkClass}
          title={options.collapsed ? item.label : undefined}
        >
          <Icon size={17} aria-hidden="true" />
          {!options.collapsed && item.label}
        </NavLink>
      </div>
    );
  };

  return (
    <div className="flex gap-6">
      {/* Mobile: schmale Leiste mit Toggle, Overlay beim Ausklappen */}
      <button
        onClick={() => setMobileOpen(true)}
        className="fixed left-0 top-16 z-20 rounded-r-lg border border-l-0 border-white/10 bg-surface px-2 py-3 text-slate-400 sm:hidden"
        aria-label="Open navigation"
      >
        <Menu size={18} aria-hidden="true" />
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
            {visibleNavItems.map((item) =>
              renderNavItem(item, { onNavigate: () => setMobileOpen(false) })
            )}
          </nav>
        </div>
      )}

      {/* Desktop: feste Sidebar, einklappbar - Toggle sitzt als eigene
          Kopfzeile ÜBER den Nav-Punkten (Design-Spec "Toggle-Kopfzeile"),
          statt isoliert unten zu hängen. */}
      <nav
        className={`hidden shrink-0 flex-col gap-1 rounded-xl bg-surface/40 p-2 sm:flex ${
          desktopCollapsed ? "w-14" : "w-48"
        } transition-all`}
      >
        <button
          onClick={() => setDesktopCollapsed((c) => !c)}
          className="flex items-center gap-2 rounded-lg px-3 py-2 text-slate-400 hover:text-white"
          aria-label={desktopCollapsed ? "Expand navigation" : "Collapse navigation"}
        >
          <Menu size={17} aria-hidden="true" />
          {!desktopCollapsed && (
            <span className="text-xs font-medium tracking-wide">Navigation</span>
          )}
        </button>
        <div className="mb-1 border-t border-white/10" />
        {visibleNavItems.map((item) => renderNavItem(item, { collapsed: desktopCollapsed }))}
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
