import { createReactBlockSpec } from "@blocknote/react";
import type { ReactCustomBlockRenderProps } from "@blocknote/react";
import { defaultProps } from "@blocknote/core";
import { FlaskConical } from "lucide-react";

const CHEM_BLOCK_TYPE = "chemStructure" as const;

const chemStructureConfig = {
  type: CHEM_BLOCK_TYPE,
  propSchema: {
    /** KET JSON — Ketcher's native format. */
    ket: { default: "" },
    /** SMILES string (molecules only) for search / display fallback. */
    smiles: { default: "" },
    /** Cached SVG preview for rendering without Ketcher. */
    svgPreview: { default: "" },

    // ── Standard file-block props (enable built-in toolbar buttons) ────
    /** Data-URI of the SVG — keeps the File* toolbar buttons active. */
    url: { default: "" },
    /** User-visible caption rendered below the structure. */
    caption: { default: "" },
    /** Filename used when downloading / saving as attachment. */
    name: { default: "" },
    /** Whether to show the inline SVG preview. */
    showPreview: { default: true },
    /** Block-level text alignment. Must match defaultProps shape. */
    textAlignment: defaultProps.textAlignment,
  },
  content: "none" as const,
};

type ChemBlockProps = ReactCustomBlockRenderProps<
  typeof CHEM_BLOCK_TYPE,
  (typeof chemStructureConfig)["propSchema"],
  "none"
>;

function ChemStructureRender(props: ChemBlockProps) {
  const { block, editor } = props;
  const { ket, svgPreview, showPreview, caption, textAlignment } = block.props;
  const isEmpty = !ket;

  const openEditor = () => {
    window.dispatchEvent(
      new CustomEvent("open-ketcher", {
        detail: { blockId: block.id, ket },
      }),
    );
  };

  return (
    <div
      data-file-block=""
      className={[
        "group/chem my-2 rounded border p-3 transition-colors",
        !showPreview && !isEmpty ? "block" : "inline-block",
        isEmpty
          ? "border-dashed border-slate-300 dark:border-slate-700"
          : "border-transparent hover:border-slate-300 dark:hover:border-slate-600",
        editor.isEditable ? "cursor-pointer" : "",
      ].join(" ")}
      style={{ textAlign: textAlignment || "left" }}
      contentEditable={false}
      onClick={editor.isEditable ? openEditor : undefined}
      title={editor.isEditable ? "Click to edit structure" : undefined}
    >
      {isEmpty ? (
        <div className="flex h-32 w-48 items-center justify-center text-sm text-slate-400">
          Click to draw a structure
        </div>
      ) : showPreview && svgPreview ? (
        <div
          className="chem-structure-preview [&>svg]:w-auto"
          dangerouslySetInnerHTML={{ __html: svgPreview }}
        />
      ) : !showPreview ? (
        <div className="bn-file-name-with-icon" contentEditable={false} draggable={false}>
          <div className="bn-file-icon">
            <FlaskConical size={24} />
          </div>
          <p className="bn-file-name">{block.props.name || "structure"}</p>
        </div>
      ) : (
        <div className="flex h-32 w-48 items-center justify-center text-sm text-slate-400">
          Loading…
        </div>
      )}

      {caption && (
        <p className="mt-1 text-center text-xs text-slate-500 dark:text-slate-400">
          {caption}
        </p>
      )}
    </div>
  );
}

/**
 * Custom BlockNote block for chemical structures.
 */
export const ChemStructureBlock = createReactBlockSpec(chemStructureConfig, {
  render: ChemStructureRender,
});
