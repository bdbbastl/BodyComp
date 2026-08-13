import { NavLink, Outlet } from "react-router-dom";

const navItems = [
  { to: "/", label: "Timeline", end: true },
  { to: "/unprocessed", label: "Import" },
  { to: "/compare", label: "Compare" },
  { to: "/statistics", label: "Statistik" },
  { to: "/settings", label: "Settings" },
];

export default function Layout() {
  return (
    <div className="min-h-screen bg-background text-slate-100">
      <header className="sticky top-0 z-20 border-b border-white/5 bg-background/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
          <span className="text-sm font-semibold tracking-wide text-white">
            BodyComp <span className="text-accent">Tracker</span>
          </span>
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
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
        <Outlet />
      </main>
    </div>
  );
}
