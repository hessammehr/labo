import { createContext, useContext, useRef, useCallback } from "react";
import type { SearchResult } from "./types";

type SearchSelectHandler = (result: SearchResult) => void;

interface SearchContextValue {
  subscribe: (handler: SearchSelectHandler) => () => void;
  dispatch: (result: SearchResult) => void;
}

const SearchContext = createContext<SearchContextValue | null>(null);

export function SearchProvider({ children }: { children: React.ReactNode }) {
  const handlersRef = useRef<Set<SearchSelectHandler>>(new Set());

  const subscribe = useCallback((handler: SearchSelectHandler) => {
    handlersRef.current.add(handler);
    return () => { handlersRef.current.delete(handler); };
  }, []);

  const dispatch = useCallback((result: SearchResult) => {
    handlersRef.current.forEach((h) => h(result));
  }, []);

  return (
    <SearchContext.Provider value={{ subscribe, dispatch }}>
      {children}
    </SearchContext.Provider>
  );
}

export function useSearchDispatch() {
  const ctx = useContext(SearchContext);
  if (!ctx) throw new Error("useSearchDispatch must be inside SearchProvider");
  return ctx.dispatch;
}

export function useSearchSubscribe() {
  const ctx = useContext(SearchContext);
  if (!ctx) throw new Error("useSearchSubscribe must be inside SearchProvider");
  return ctx.subscribe;
}
