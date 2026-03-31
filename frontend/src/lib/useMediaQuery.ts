import { useEffect, useState } from "react";

/**
 * Returns true when the viewport matches the given media query string.
 * Updates reactively on window resize / orientation change.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window !== "undefined" ? window.matchMedia(query).matches : false,
  );

  useEffect(() => {
    const mql = window.matchMedia(query);
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, [query]);

  return matches;
}

/**
 * True when the viewport is wide enough to show sidebars inline
 * (pushing the editor) rather than as overlays.
 */
export function useIsWide(): boolean {
  return useMediaQuery("(min-width: 1024px)");
}
