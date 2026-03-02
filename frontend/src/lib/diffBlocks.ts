/**
 * Compute a compressed diff summary between two BlockNote block snapshots.
 *
 * Reports:
 *  - blocks added / removed (by multiset comparison of block content strings)
 *  - the text of the highest-level heading that was added or removed
 */

type ContentBlock = Record<string, unknown>;

export interface DiffSummary {
  added: number;
  removed: number;
  /** Text of the most prominent heading that changed, if any. */
  headingContext: string | null;
  /** Whether that heading was added or removed. */
  headingAction: "added" | "removed" | null;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Produce a stable string key for a single block (type + flattened text). */
function blockKey(block: ContentBlock): string {
  const type = (block.type as string) ?? "paragraph";
  const text = flattenText(block.content as Array<Record<string, unknown>> | undefined);
  return `${type}::${text}`;
}

/** Flatten inline content nodes into a plain string. */
function flattenText(content: Array<Record<string, unknown>> | undefined): string {
  if (!content) return "";
  return content
    .map((node) => {
      if (typeof node === "string") return node;
      const t = (node.text as string) ?? "";
      const nested = node.content as Array<Record<string, unknown>> | undefined;
      return t || flattenText(nested);
    })
    .join("");
}

/** Recursively collect block keys from a tree of blocks. */
function collectBlockKeys(blocks: ContentBlock[]): string[] {
  const keys: string[] = [];
  for (const block of blocks) {
    keys.push(blockKey(block));
    const children = block.children as ContentBlock[] | undefined;
    if (children?.length) keys.push(...collectBlockKeys(children));
  }
  return keys;
}

interface HeadingInfo {
  level: number;
  text: string;
}

function extractHeadings(blocks: ContentBlock[]): HeadingInfo[] {
  const headings: HeadingInfo[] = [];
  for (const block of blocks) {
    if ((block.type as string) === "heading") {
      const props = block.props as Record<string, unknown> | undefined;
      const text = flattenText(block.content as Array<Record<string, unknown>> | undefined);
      if (text) headings.push({ level: (props?.level as number) ?? 1, text });
    }
    const children = block.children as ContentBlock[] | undefined;
    if (children?.length) headings.push(...extractHeadings(children));
  }
  return headings;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export function computeDiff(before: ContentBlock[], after: ContentBlock[]): DiffSummary {
  // --- block-level +/- via multiset difference ---
  const beforeKeys = collectBlockKeys(before);
  const afterKeys = collectBlockKeys(after);

  const beforeCounts = new Map<string, number>();
  for (const k of beforeKeys) beforeCounts.set(k, (beforeCounts.get(k) ?? 0) + 1);

  const afterCounts = new Map<string, number>();
  for (const k of afterKeys) afterCounts.set(k, (afterCounts.get(k) ?? 0) + 1);

  let added = 0;
  let removed = 0;
  const allKeys = new Set([...beforeCounts.keys(), ...afterCounts.keys()]);
  for (const k of allKeys) {
    const b = beforeCounts.get(k) ?? 0;
    const a = afterCounts.get(k) ?? 0;
    if (a > b) added += a - b;
    if (b > a) removed += b - a;
  }

  // --- heading context ---
  const beforeHeadings = extractHeadings(before);
  const afterHeadings = extractHeadings(after);

  const beforeHeadingTexts = new Set(beforeHeadings.map((h) => h.text));
  const afterHeadingTexts = new Set(afterHeadings.map((h) => h.text));

  let headingContext: string | null = null;
  let headingAction: "added" | "removed" | null = null;
  let bestLevel = Infinity;

  for (const h of afterHeadings) {
    if (!beforeHeadingTexts.has(h.text) && h.level < bestLevel) {
      bestLevel = h.level;
      headingContext = h.text;
      headingAction = "added";
    }
  }
  for (const h of beforeHeadings) {
    if (!afterHeadingTexts.has(h.text) && h.level < bestLevel) {
      bestLevel = h.level;
      headingContext = h.text;
      headingAction = "removed";
    }
  }

  return { added, removed, headingContext, headingAction };
}
