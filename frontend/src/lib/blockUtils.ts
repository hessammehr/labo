/**
 * Utilities for working with BlockNote block structures.
 *
 * BlockNote's block schema is not uniform: most blocks carry
 * `content: InlineContentNode[]` (an array), but table blocks carry
 * `content: { type: "tableContent", rows: [...] }` (an object).  Any code
 * that traverses blocks should go through the helpers here rather than
 * accessing `.content` directly, so that new/unusual block types only need
 * to be handled in one place.
 */

export type InlineNode = Record<string, unknown>;
export type ContentBlock = Record<string, unknown>;

// ---------------------------------------------------------------------------
// tableContent helpers
// ---------------------------------------------------------------------------

interface TableCell {
  type: "tableCell";
  content: InlineNode[];
  props?: Record<string, unknown>;
}

interface TableRow {
  cells: TableCell[];
}

interface TableContent {
  type: "tableContent";
  columnWidths?: (number | null)[];
  rows: TableRow[];
}

/** Return true when a block's content field is a tableContent object. */
export function isTableContent(content: unknown): content is TableContent {
  return (
    typeof content === "object" &&
    content !== null &&
    !Array.isArray(content) &&
    (content as Record<string, unknown>).type === "tableContent"
  );
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Extract all inline content nodes from a block as a flat array, regardless
 * of block type.
 *
 * - Regular blocks   → `content` array is returned as-is.
 * - Table blocks     → inline nodes from all cells are concatenated.
 * - Unknown shapes   → empty array (never throws).
 */
export function blockInlineContent(block: ContentBlock): InlineNode[] {
  const content = block.content;

  if (!content) return [];

  if (Array.isArray(content)) {
    return content as InlineNode[];
  }

  if (isTableContent(content)) {
    return content.rows.flatMap((row) =>
      row.cells.flatMap((cell) => cell.content ?? [])
    );
  }

  return [];
}

/**
 * Extract a plain-text string from a block's inline content, recursively
 * descending into nested content.
 */
export function blockText(block: ContentBlock): string {
  return flattenInlineText(blockInlineContent(block));
}

/** Recursively flatten an array of inline nodes into a plain string. */
export function flattenInlineText(nodes: InlineNode[]): string {
  return nodes
    .map((node) => {
      if (typeof node === "string") return node;
      const t = (node.text as string) ?? "";
      const nested = node.content as InlineNode[] | undefined;
      return t || (nested ? flattenInlineText(nested) : "");
    })
    .join("");
}
