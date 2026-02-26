import { Link, Outlet } from "react-router-dom";

import { useAuth } from "../lib/auth";

export function AppShell() {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <header className="border-b bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center justify-between px-4 py-3">
          <Link to="/" className="text-lg font-semibold">
            Labo
          </Link>
          <div className="flex items-center gap-4 text-sm">
            <span className="text-slate-600 dark:text-slate-300">{user?.email}</span>
            <button
              onClick={logout}
              className="rounded border border-slate-300 px-3 py-1 hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
            >
              Logout
            </button>
          </div>
        </div>
      </header>
      <main className="px-4 py-4">
        <Outlet />
      </main>
    </div>
  );
}
