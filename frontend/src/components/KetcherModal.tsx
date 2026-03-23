import { lazy, Suspense, useEffect, useRef, useState, useCallback } from "react";
import type { Ketcher } from "ketcher-core";

// Lazy-load the Editor component (keeps ~5 MB out of initial bundle)
const KetcherEditor = lazy(() =>
  import("ketcher-react").then((m) => ({ default: m.Editor })),
);

import "ketcher-react/dist/index.css";

type Props = {
  open: boolean;
  /** KET JSON string to load into the editor (empty = blank canvas) */
  initialKet: string;
  onSave: (ket: string, smiles: string, svg: string) => void;
  onClose: () => void;
};

/** Check if the page is currently in dark mode (Tailwind .dark on <html>). */
function isDarkMode(): boolean {
  return document.documentElement.classList.contains("dark");
}

export function KetcherModal({ open, initialKet, onSave, onClose }: Props) {
  const ketcherRef = useRef<Ketcher | null>(null);

  // Load StandaloneStructServiceProvider lazily on first open
  const [structServiceProvider, setStructServiceProvider] = useState<any>(null);
  useEffect(() => {
    if (!open || structServiceProvider) return;
    import("ketcher-standalone").then((m) => {
      setStructServiceProvider(new m.StandaloneStructServiceProvider());
    });
  }, [open, structServiceProvider]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", handler, true);
    return () => window.removeEventListener("keydown", handler, true);
  }, [open, onClose]);

  const handleInit = useCallback(
    (ketcher: Ketcher) => {
      ketcherRef.current = ketcher;
      if (initialKet) {
        ketcher.setMolecule(initialKet);
      }
    },
    [initialKet],
  );

  const handleSave = useCallback(async () => {
    const ketcher = ketcherRef.current;
    if (!ketcher) return;
    try {
      // KET is Ketcher's native JSON format — supports molecules, reactions,
      // R-groups, S-groups, etc.  No format limitations.
      const ket = await ketcher.getKet();

      // SMILES is best-effort (only works for simple molecules, not reactions)
      let smiles = "";
      try {
        smiles = await ketcher.getSmiles();
      } catch {
        // Reactions / complex structures can't be represented as SMILES
      }

      // SVG preview
      let svg = "";
      try {
        const result = await ketcher.generateImage(ket, {
          outputFormat: "svg",
          // Indigo default bond-length is 40px in the editor.
          // 30 = 75% of default → structures render ~25% smaller.
          "bond-length": 30,
        });
        if (result instanceof Blob) {
          svg = await result.text();
        } else {
          svg = String(result);
        }
      } catch {
        // Preview generation can fail for empty canvases, etc.
      }

      onSave(ket, smiles, svg);
    } catch (err) {
      console.error("Ketcher save error:", err);
    }
  }, [onSave]);

  if (!open) return null;

  // Ketcher has no built-in dark mode. We apply a CSS filter inversion on
  // the Ketcher container when the page is in dark mode. This gives a
  // convincing dark look without forking Ketcher's internals.
  const dark = isDarkMode();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="flex h-[85vh] w-[85vw] flex-col overflow-hidden rounded-lg bg-white shadow-2xl dark:bg-slate-900">
        {/* Toolbar */}
        <div className="flex shrink-0 items-center justify-between border-b border-slate-200 px-4 py-2 dark:border-slate-700">
          <span className="font-semibold dark:text-slate-100">
            Chemical Structure Editor
          </span>
          <div className="flex gap-2">
            <button
              onClick={handleSave}
              className="rounded bg-blue-600 px-4 py-1 text-sm text-white hover:bg-blue-700"
            >
              Save
            </button>
            <button
              onClick={onClose}
              className="rounded border border-slate-300 px-4 py-1 text-sm hover:bg-slate-100 dark:border-slate-600 dark:hover:bg-slate-800 dark:text-slate-100"
            >
              Cancel
            </button>
          </div>
        </div>

        {/* Ketcher canvas — CSS filter inversion for dark mode */}
        <div
          className="min-h-0 flex-1"
          style={dark ? { filter: "invert(1) hue-rotate(180deg)" } : undefined}
        >
          {structServiceProvider ? (
            <Suspense
              fallback={
                <div className="flex h-full items-center justify-center text-slate-400">
                  Loading editor…
                </div>
              }
            >
              <KetcherEditor
                staticResourcesUrl={process.env.PUBLIC_URL ?? "/"}
                structServiceProvider={structServiceProvider}
                errorHandler={(message: string) =>
                  console.error("Ketcher:", message)
                }
                onInit={handleInit}
              />
            </Suspense>
          ) : (
            <div className="flex h-full items-center justify-center text-slate-400">
              Loading editor…
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
