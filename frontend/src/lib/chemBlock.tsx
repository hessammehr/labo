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

function ChemStructureRender(props: ChemBlockProps) {
  const { block, editor } = props;
  const { ket, svgPreview } = block.props;
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
      className={`my-2 inline-block rounded border border-slate-300 p-3 dark:border-slate-700 ${
        editor.isEditable ? "cursor-pointer hover:border-blue-400 dark:hover:border-blue-500" : ""
      }`}
      contentEditable={false}
      onClick={editor.isEditable ? openEditor : undefined}
      title={editor.isEditable ? "Click to edit structure" : undefined}
    >
      {svgPreview ? (
        <div
          className="chem-structure-preview max-h-96 max-w-full [&>svg]:max-h-96 [&>svg]:w-auto"
          dangerouslySetInnerHTML={{ __html: svgPreview }}
        />
      ) : (
        <div className="flex h-32 w-48 items-center justify-center text-sm text-slate-400">
          {isEmpty ? "Click to draw a structure" : "Loading…"}
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
export const ChemStructureBlock = createReactBlockSpec(
  chemStructureConfig,
  { render: ChemStructureRender },
);
