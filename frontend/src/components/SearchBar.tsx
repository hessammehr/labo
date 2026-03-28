import { useCallback, useEffect, useRef, useState } from "react";
import { FileText, Search, X } from "lucide-react";
import { api } from "../lib/api";
import type { SearchResult } from "../lib/types";
import { LabBook } from "./icons";

interface SearchBarProps {
  onSelect: (result: SearchResult) => void;
}

export function SearchBar({ onSelect }: SearchBarProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  // Cmd+K / Ctrl+K focuses the input
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

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
    setDropdownOpen(true);
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
    setDropdownOpen(false);
    setQuery("");
    setResults([]);
    inputRef.current?.blur();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!dropdownOpen) return;
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
        setDropdownOpen(false);
        inputRef.current?.blur();
        break;
    }
  };

  const hasQuery = query.trim().length > 0;
  const showDropdown = dropdownOpen && hasQuery;

  return (
    <div ref={containerRef} className="relative w-full min-w-0 max-w-lg" onKeyDown={onKeyDown}>
      {/* Always-visible search input */}
      <div className="flex items-center gap-2 rounded border border-slate-300 bg-slate-50 px-2.5 dark:border-slate-700 dark:bg-slate-800">
        <Search size={14} className="shrink-0 text-slate-400" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => onInputChange(e.target.value)}
          onFocus={() => { if (hasQuery) setDropdownOpen(true); }}
          placeholder="Search…"
          className="flex-1 min-w-0 bg-transparent py-1.5 text-sm outline-none placeholder:text-slate-400 dark:text-slate-100"
        />
        {query ? (
          <button
            onClick={() => { setQuery(""); setResults([]); setDropdownOpen(false); inputRef.current?.focus(); }}
            className="shrink-0 rounded p-0.5 hover:bg-slate-200 dark:hover:bg-slate-700"
          >
            <X size={12} className="text-slate-400" />
          </button>
        ) : (
          <kbd className="hidden sm:inline-block shrink-0 rounded border border-slate-300 px-1.5 py-0.5 text-[10px] font-medium text-slate-400 dark:border-slate-600">
            ⌘K
          </kbd>
        )}
      </div>

      {/* Results dropdown */}
      {showDropdown && (
        <div className="fixed left-2 right-2 sm:absolute sm:left-0 sm:right-0 top-auto z-50 mt-1 rounded border border-slate-300 bg-white shadow-lg dark:border-slate-600 dark:bg-slate-900">
          <div ref={listRef} className="max-h-[60vh] overflow-y-auto">
            {loading && results.length === 0 && (
              <div className="px-4 py-4 text-center text-sm text-slate-400">Searching…</div>
            )}

            {!loading && results.length === 0 && (
              <div className="px-4 py-4 text-center text-sm text-slate-400">No results found</div>
            )}

            {results.map((result, idx) => (
              <button
                key={`${result.type}-${result.id}`}
                className={`flex w-full items-center gap-3 px-3 py-1.5 text-left text-sm ${
                  idx === activeIndex
                    ? "bg-blue-600 text-white [&_*]:text-white"
                    : "text-slate-900 dark:text-slate-100"
                }`}
                onClick={() => selectResult(result)}
                onMouseEnter={() => setActiveIndex(idx)}
              >
                <div className="shrink-0">
                  {result.type === "notebook" ? (
                    <LabBook size={16} className={idx === activeIndex ? "text-white" : "text-slate-400"} />
                  ) : (
                    <FileText size={16} className={idx === activeIndex ? "text-white" : "text-slate-400"} />
                  )}
                </div>
                <div className="min-w-0 flex-1 truncate">
                  <span className="font-medium">{result.title}</span>
                  {result.type === "entry" && result.notebook_title && (
                    <span className={`ml-2 text-xs ${idx === activeIndex ? "text-blue-100" : "text-slate-400"}`}>
                      {result.notebook_title}
                    </span>
                  )}
                </div>
                {result.snippet && result.snippet !== result.title && (
                  <div className={`shrink-0 truncate max-w-[40%] text-xs ${idx === activeIndex ? "text-blue-100" : "text-slate-500 dark:text-slate-400"}`}>
                    {result.snippet}
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
