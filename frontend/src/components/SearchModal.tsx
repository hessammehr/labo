import { useCallback, useEffect, useRef, useState } from "react";
import { FileText, Search, X } from "lucide-react";
import { api } from "../lib/api";
import type { SearchResult } from "../lib/types";
import { LabBook } from "./icons";

interface SearchModalProps {
  open: boolean;
  onClose: () => void;
  onSelect: (result: SearchResult) => void;
}

export function SearchModal({ open, onClose, onSelect }: SearchModalProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  // Focus input when opening
  useEffect(() => {
    if (open) {
      setQuery("");
      setResults([]);
      setActiveIndex(0);
      // Small delay to ensure the DOM is ready
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  // Debounced search
  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) {
      setResults([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const { data } = await api.get<SearchResult[]>("/search/", { params: { q } });
      setResults(data);
      setActiveIndex(0);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const onInputChange = (value: string) => {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(value), 200);
  };

  // Scroll active item into view
  useEffect(() => {
    if (!listRef.current) return;
    const activeEl = listRef.current.children[activeIndex] as HTMLElement | undefined;
    activeEl?.scrollIntoView({ block: "nearest" });
  }, [activeIndex]);

  const selectResult = (result: SearchResult) => {
    onSelect(result);
    onClose();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setActiveIndex((i) => Math.min(i + 1, results.length - 1));
        break;
      case "ArrowUp":
        e.preventDefault();
        setActiveIndex((i) => Math.max(i - 1, 0));
        break;
      case "Enter":
        e.preventDefault();
        if (results[activeIndex]) selectResult(results[activeIndex]);
        break;
      case "Escape":
        e.preventDefault();
        onClose();
        break;
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]"
      onClick={onClose}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40" />

      {/* Modal */}
      <div
        className="relative w-full max-w-xl rounded-lg border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={onKeyDown}
      >
        {/* Search input */}
        <div className="flex items-center gap-2 border-b border-slate-200 px-3 dark:border-slate-700">
          <Search size={16} className="shrink-0 text-slate-400" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => onInputChange(e.target.value)}
            placeholder="Search notebooks and entries…"
            className="flex-1 bg-transparent py-3 text-sm outline-none placeholder:text-slate-400 dark:text-slate-100"
          />
          {query && (
            <button
              onClick={() => { setQuery(""); setResults([]); inputRef.current?.focus(); }}
              className="rounded p-0.5 hover:bg-slate-100 dark:hover:bg-slate-800"
            >
              <X size={14} className="text-slate-400" />
            </button>
          )}
          <kbd className="hidden sm:inline-block rounded border border-slate-300 px-1.5 py-0.5 text-[10px] font-medium text-slate-400 dark:border-slate-600">
            ESC
          </kbd>
        </div>

        {/* Results */}
        <div ref={listRef} className="max-h-80 overflow-y-auto">
          {loading && results.length === 0 && (
            <div className="px-4 py-6 text-center text-sm text-slate-400">Searching…</div>
          )}

          {!loading && query.trim() && results.length === 0 && (
            <div className="px-4 py-6 text-center text-sm text-slate-400">No results found</div>
          )}

          {!query.trim() && (
            <div className="px-4 py-6 text-center text-sm text-slate-400">
              Type to search across all your notebooks and entries
            </div>
          )}

          {results.map((result, idx) => (
            <button
              key={`${result.type}-${result.id}`}
              className={`flex w-full items-start gap-3 px-3 py-2 text-left text-sm transition-colors ${
                idx === activeIndex
                  ? "bg-blue-50 dark:bg-blue-950/50"
                  : "hover:bg-slate-50 dark:hover:bg-slate-800/50"
              }`}
              onClick={() => selectResult(result)}
              onMouseEnter={() => setActiveIndex(idx)}
            >
              <div className="mt-0.5 shrink-0">
                {result.type === "notebook" ? (
                  <LabBook size={16} className="text-slate-400" />
                ) : (
                  <FileText size={16} className="text-slate-400" />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className="font-medium text-slate-900 dark:text-slate-100 truncate">
                  {result.title}
                </div>
                {result.type === "entry" && result.notebook_title && (
                  <div className="text-xs text-slate-400 truncate">
                    {result.notebook_title}
                  </div>
                )}
                {result.snippet && (
                  <div className="mt-0.5 text-xs text-slate-500 dark:text-slate-400 line-clamp-2">
                    {result.snippet}
                  </div>
                )}
              </div>
              <div className="mt-0.5 shrink-0">
                <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                  {result.type === "notebook" ? "Notebook" : "Entry"}
                </span>
              </div>
            </button>
          ))}
        </div>

        {/* Footer hint */}
        {results.length > 0 && (
          <div className="flex items-center gap-3 border-t border-slate-200 px-3 py-1.5 text-[10px] text-slate-400 dark:border-slate-700">
            <span><kbd className="rounded border border-slate-300 px-1 dark:border-slate-600">↑↓</kbd> navigate</span>
            <span><kbd className="rounded border border-slate-300 px-1 dark:border-slate-600">↵</kbd> open</span>
            <span><kbd className="rounded border border-slate-300 px-1 dark:border-slate-600">esc</kbd> close</span>
          </div>
        )}
      </div>
    </div>
  );
}
