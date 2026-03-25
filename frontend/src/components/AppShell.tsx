import { Link, Outlet } from "react-router-dom";
import { Moon, Sun } from "lucide-react";

import { useAuth } from "../lib/auth";
import { useTheme } from "../lib/useTheme";
import { useSearchDispatch } from "../lib/searchContext";
import { Logo } from "./Logo";
import { SearchBar } from "./SearchBar";


export function AppShell() {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const dispatchSearch = useSearchDispatch();

  return (
    <div className="h-screen flex flex-col bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <header className="shrink-0 border-b bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="grid grid-cols-[auto_1fr_auto] items-center gap-4 px-4 py-2">
          <Link to="/" className="shrink-0">
            <Logo className="h-8 w-auto" />
          </Link>
          <div className="flex justify-center">
            <SearchBar onSelect={dispatchSearch} />
          </div>
          <div className="flex shrink-0 items-center gap-4 text-sm">
            <span className="text-slate-600 dark:text-slate-300">{user?.email}</span>
            <button
              onClick={toggle}
              className="rounded p-1.5 hover:bg-slate-100 dark:hover:bg-slate-800"
              aria-label="Toggle dark mode"
            >
              {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <button
              onClick={logout}
              className="rounded border border-slate-300 px-3 py-1 hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
            >
              Logout
            </button>
          </div>
        </div>
      </header>
      <main className="min-h-0 flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}
