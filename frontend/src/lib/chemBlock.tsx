import { useCallback, useRef, useState } from "react";
import { createReactBlockSpec } from "@blocknote/react";
import type { ReactCustomBlockRenderProps } from "@blocknote/react";

const CHEM_BLOCK_TYPE = "chemStructure" as const;

const chemStructureConfig = {
  type: CHEM_BLOCK_TYPE,
  propSchema: {
    /** KET JSON — Ketcher's native format. Supports molecules, reactions,
     *  R-groups, S-groups, etc.  This is the canonical representation. */
    ket: { default: "" },
    /** SMILES string (molecules only) for search / display fallback */
    smiles: { default: "" },
    /** Cached SVG preview for rendering without Ketcher */
    svgPreview: { default: "" },
  },
  content: "none" as const,
};

type ChemBlockProps = ReactCustomBlockRenderProps<
  typeof CHEM_BLOCK_TYPE,
  (typeof chemStructureConfig)["propSchema"],
  "none"
>;

/** Dispatch a custom event to request saving the SVG as an attachment. */
function dispatchExportSvg(
  svgPreview: string,
  action: "download" | "attachment",
) {
  window.dispatchEvent(
    new CustomEvent("chem-export-svg", {
      detail: { svgPreview, action },
    }),
  );
}

function ChemStructureRender(props: ChemBlockProps) {
  const { block, editor } = props;
  const { ket, svgPreview } = block.props;
  const isEmpty = !ket;

  // --- Context menu state ---
  const [menuPos, setMenuPos] = useState<{ x: number; y: number } | null>(
    null,
  );
  const menuRef = useRef<HTMLDivElement>(null);

  const openEditor = () => {
    window.dispatchEvent(
      new CustomEvent("open-ketcher", {
        detail: { blockId: block.id, ket },
      }),
    );
  };

  const handleContextMenu = useCallback(
    (e: React.MouseEvent) => {
      if (!svgPreview) return;
      e.preventDefault();
      e.stopPropagation();
      setMenuPos({ x: e.clientX, y: e.clientY });
      const close = () => {
        setMenuPos(null);
        document.removeEventListener("click", close);
      };
      // Close on next click anywhere
      setTimeout(() => document.addEventListener("click", close), 0);
    },
    [svgPreview],
  );

  return (
    <div
      className={[
        "group/chem my-2 inline-block rounded border p-3 transition-colors",
        // No border at rest; visible border on hover / editable
        isEmpty
          ? "border-dashed border-slate-300 dark:border-slate-700"
          : "border-transparent hover:border-slate-300 dark:hover:border-slate-600",
        editor.isEditable ? "cursor-pointer" : "",
      ].join(" ")}
      contentEditable={false}
      onClick={editor.isEditable ? openEditor : undefined}
      onContextMenu={handleContextMenu}
      title={editor.isEditable ? "Click to edit structure" : undefined}
    >
      {svgPreview ? (
        <div
          className="chem-structure-preview [&>svg]:w-auto"
          dangerouslySetInnerHTML={{ __html: svgPreview }}
        />
      ) : (
        <div className="flex h-32 w-48 items-center justify-center text-sm text-slate-400">
          {isEmpty ? "Click to draw a structure" : "Loading…"}
        </div>
      )}

      {/* Context menu */}
      {menuPos && (
        <div
          ref={menuRef}
          className="fixed z-50 min-w-[160px] rounded border border-slate-200 bg-white py-1 text-sm shadow-lg dark:border-slate-700 dark:bg-slate-800"
          style={{ left: menuPos.x, top: menuPos.y }}
        >
          <button
            className="w-full px-3 py-1.5 text-left hover:bg-slate-100 dark:hover:bg-slate-700 dark:text-slate-200"
            onClick={(e) => {
              e.stopPropagation();
              dispatchExportSvg(svgPreview, "download");
              setMenuPos(null);
            }}
          >
            Download as SVG
          </button>
          <button
            className="w-full px-3 py-1.5 text-left hover:bg-slate-100 dark:hover:bg-slate-700 dark:text-slate-200"
            onClick={(e) => {
              e.stopPropagation();
              dispatchExportSvg(svgPreview, "attachment");
              setMenuPos(null);
            }}
          >
            Save to notebook as attachment
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * Custom BlockNote block for chemical structures.
 *
 * Call the returned factory (no options needed) to get the block spec, then
 * merge it into your schema's `blockSpecs`.
 */
export const ChemStructureBlock = createReactBlockSpec(chemStructureConfig, {
  render: ChemStructureRender,
});
