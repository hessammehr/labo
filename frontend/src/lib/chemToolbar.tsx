/**
 * Custom formatting-toolbar buttons for the chemStructure block.
 *
 * Most toolbar buttons (Caption, Rename, Delete, Preview, Alignment) are
 * handled by BlockNote's built-in File* / TextAlign buttons — our block's
 * propSchema includes the props they check for (`url`, `caption`, `name`,
 * `showPreview`, `textAlignment`).
 *
 * Only three buttons need custom implementations:
 *   – Replace: clears the structure (built-in opens a file picker panel)
 *   – Download: exports SVG from the `svgPreview` prop (built-in opens `url`)
 *   – Attachment: saves SVG to notebook — no built-in equivalent
 */

import { useCallback } from "react";
import {
  useBlockNoteEditor,
  useEditorState,
  useComponentsContext,
} from "@blocknote/react";
import type {
  BlockSchema,
  InlineContentSchema,
  StyleSchema,
} from "@blocknote/core";
import {
  RiImageEditFill,
  RiDownload2Fill,
  RiAttachment2,
} from "react-icons/ri";

type ChemBlockLike = {
  id: string;
  props: Record<string, unknown>;
};

/** Build an SVG filename from the block's name (set via Rename). */
function chemFilename(block: ChemBlockLike): string {
  const raw = block.props.name;
  const name = typeof raw === "string" ? raw : "";
  const base = name || `structure-${Date.now()}`;
  return base.endsWith(".svg") ? base : `${base}.svg`;
}

// ---------------------------------------------------------------------------
// Shared hook: selected chemStructure block (or undefined)
// ---------------------------------------------------------------------------

function useSelectedChemBlock(opts?: { requireEditable?: boolean }) {
  const editor = useBlockNoteEditor<
    BlockSchema,
    InlineContentSchema,
    StyleSchema
  >();

  return useEditorState({
    editor,
    selector: ({ editor }) => {
      if (opts?.requireEditable && !editor.isEditable) return undefined;

      const blocks = editor.getSelection()?.blocks || [
        editor.getTextCursorPosition().block,
      ];
      if (blocks.length !== 1) return undefined;
      const b = blocks[0];
      return b.type === "chemStructure" ? b : undefined;
    },
  });
}

// ---------------------------------------------------------------------------
// Replace (clear structure) — replaces built-in FileReplaceButton
// ---------------------------------------------------------------------------

export const ChemReplaceButton = () => {
  const Components = useComponentsContext()!;
  const editor = useBlockNoteEditor<
    BlockSchema,
    InlineContentSchema,
    StyleSchema
  >();
  const block = useSelectedChemBlock({ requireEditable: true });

  const onClick = useCallback(() => {
    if (!block) return;
    editor.updateBlock(block.id, {
      props: { ket: "", smiles: "", svgPreview: "", url: "" } as never,
    });
    editor.focus();
  }, [block, editor]);

  if (!block) return null;

  return (
    <Components.FormattingToolbar.Button
      className="bn-button"
      label="Replace structure"
      mainTooltip="Replace structure"
      icon={<RiImageEditFill />}
      onClick={onClick}
    />
  );
};

// ---------------------------------------------------------------------------
// Download SVG — replaces built-in FileDownloadButton
// ---------------------------------------------------------------------------

export const ChemDownloadButton = () => {
  const Components = useComponentsContext()!;
  const block = useSelectedChemBlock();

  const onClick = useCallback(() => {
    if (!block) return;
    const svgProp = block.props.svgPreview;
    const svg = typeof svgProp === "string" ? svgProp : "";
    if (!svg) return;
    const filename = chemFilename(block);
    const blob = new Blob([svg], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }, [block]);

  if (!block || typeof block.props.svgPreview !== "string" || !block.props.svgPreview) return null;

  return (
    <Components.FormattingToolbar.Button
      className="bn-button"
      label="Download SVG"
      mainTooltip="Download SVG"
      icon={<RiDownload2Fill />}
      onClick={onClick}
    />
  );
};

// ---------------------------------------------------------------------------
// Save as attachment (paperclip) — no built-in equivalent
// ---------------------------------------------------------------------------

export const ChemAttachmentButton = () => {
  const Components = useComponentsContext()!;
  const block = useSelectedChemBlock();

  const onClick = useCallback(() => {
    if (!block) return;
    const svgProp = block.props.svgPreview;
    const svg = typeof svgProp === "string" ? svgProp : "";
    if (!svg) return;
    const filename = chemFilename(block);
    window.dispatchEvent(
      new CustomEvent("chem-export-svg", {
        detail: { svgPreview: svg, action: "attachment", filename },
      }),
    );
  }, [block]);

  if (!block || typeof block.props.svgPreview !== "string" || !block.props.svgPreview) return null;

  return (
    <Components.FormattingToolbar.Button
      className="bn-button"
      label="Save as attachment"
      mainTooltip="Save as attachment"
      icon={<RiAttachment2 />}
      onClick={onClick}
    />
  );
};
