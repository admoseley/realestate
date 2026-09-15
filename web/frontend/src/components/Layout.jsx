import { useEffect, useSyncExternalStore } from "react";
import { Outlet, NavLink } from "react-router-dom";
import { isDatabaseWaking, subscribeDatabaseWaking, warmUpDatabase } from "../api/client";

const NAV = [
  { to: "/",             label: "Dashboard" },
  { to: "/sheriff-sale", label: "Sheriff Sale" },
  { to: "/spot-check",   label: "Spot Check" },
  { to: "/history",      label: "History" },
];

export default function Layout() {
  const databaseWaking = useSyncExternalStore(subscribeDatabaseWaking, isDatabaseWaking);

  // Layout wraps every page, so this runs once per app load: it starts a
  // paused database resuming before the page's own requests need it.
  useEffect(() => { warmUpDatabase(); }, []);

  return (
    <div className="flex h-screen overflow-hidden bg-brand-gray">
      {/* Sidebar */}
      <aside className="w-56 flex-shrink-0 bg-brand-charcoal flex flex-col">
        <div className="px-5 py-4 border-b border-white/10">
          <p className="text-brand-orange font-bold text-sm leading-tight">
            Estella Wilson<br />
            <span className="text-white/70 font-normal">Properties LLC</span>
          </p>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-1">
          {NAV.map(({ to, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `block px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-brand-orange text-white"
                    : "text-white/70 hover:bg-white/10 hover:text-white"
                }`
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>

      {/* Main area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="h-14 bg-brand-orange flex items-center px-6 flex-shrink-0">
          <span className="text-white font-bold text-lg tracking-wide">
            Real Estate Investment Analyzer
          </span>
        </header>

        {databaseWaking && (
          <div role="status" className="bg-amber-50 border-b border-amber-200 text-amber-800 text-sm px-6 py-2 flex items-center gap-2 flex-shrink-0">
            <span className="inline-block w-3 h-3 border-2 border-amber-600 border-t-transparent rounded-full animate-spin" />
            Waking up the database… this can take up to a minute after a quiet period.
          </div>
        )}

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
