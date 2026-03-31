import { createContext, useContext, useEffect, useRef, useState } from "react";
import { Link, Outlet } from "react-router-dom";
import { Moon, Sun } from "lucide-react";

import { useAuth } from "../lib/auth";
import { useTheme } from "../lib/useTheme";
import { useSearchDispatch } from "../lib/searchContext";
import { useIsWide } from "../lib/useMediaQuery";
import { Logo } from "./Logo";
import { SearchBar } from "./SearchBar";

// ── Panel context ────────────────────────────────────────────────────

interface PanelContextValue {
  leftOpen: boolean;
  setLeftOpen: (open: boolean | ((prev: boolean) => boolean)) => void;
  rightOpen: boolean;
  setRightOpen: (open: boolean | ((prev: boolean) => boolean)) => void;
  isWide: boolean;
}

const PanelContext = createContext<PanelContextValue>({
  leftOpen: true,
  setLeftOpen: () => {},
  rightOpen: false,
  setRightOpen: () => {},
  isWide: true,
});

export function usePanels() {
  return useContext(PanelContext);
}

export function AppShell() {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const dispatchSearch = useSearchDispatch();
  const isWide = useIsWide();

  const [leftOpen, setLeftOpen] = useState(isWide);
  const [rightOpen, setRightOpen] = useState(false);

  const prevIsWide = useRef(isWide);
  useEffect(() => {
    if (isWide !== prevIsWide.current) {
      prevIsWide.current = isWide;
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLeftOpen(isWide);
      if (!isWide) {
        setRightOpen(false);
      }
    }
  }, [isWide]);

  return (
    <PanelContext.Provider value={{ leftOpen, setLeftOpen, rightOpen, setRightOpen, isWide }}>
      <div className="h-screen flex flex-col bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
        <header className="shrink-0 border-b bg-white dark:border-slate-800 dark:bg-slate-900 relative z-[100]">
          <div className="flex items-center gap-2 px-3 py-2">
            <Link to="/" className="shrink-0">
              <Logo className="h-8 w-auto" />
            </Link>

            <div className="flex flex-1 justify-center min-w-0">
              <SearchBar onSelect={dispatchSearch} />
            </div>

            <div className="flex shrink-0 items-center gap-2 text-sm">
              {isWide && (
                <span className="text-slate-600 dark:text-slate-300">{user?.email}</span>
              )}

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
    </PanelContext.Provider>
  );
}
