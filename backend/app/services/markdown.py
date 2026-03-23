"""Convert between BlockNote JSON blocks and Markdown."""

from __future__ import annotations

import base64
import re


def blocks_to_markdown(blocks: list[dict], title: str | None = None) -> str:
    """Convert a list of BlockNote blocks to a Markdown string.

    If *title* is provided it is emitted as a ``# title`` header before the
    body content.
    """
    lines: list[str] = []
    if title:
        lines.append(f"# {title}")
        lines.append("")

    _render_blocks(blocks, lines, indent=0, counters={})

    # Ensure trailing newline
    text = "\n".join(lines)
    if text and not text.endswith("\n"):
        text += "\n"
    return text


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _render_blocks(
    blocks: list[dict],
    lines: list[str],
    indent: int,
    counters: dict[int, int],
) -> None:
    prev_type: str | None = None
    for block in blocks:
        btype = block.get("type", "paragraph")

        # Reset the numbered-list counter for this indent level when the run
        # of numberedListItem blocks is interrupted.
        if btype != "numberedListItem" and prev_type == "numberedListItem":
            counters.pop(indent, None)

        _render_block(block, lines, indent, counters)
        prev_type = btype


def _render_block(
    block: dict,
    lines: list[str],
    indent: int,
    counters: dict[int, int],
) -> None:
    btype = block.get("type", "paragraph")
    props = block.get("props", {})
    content = block.get("content", [])
    children = block.get("children", [])
    prefix = "    " * indent
    inline = _render_inline(content)

    if btype == "paragraph":
        lines.append(f"{prefix}{inline}")
        lines.append("")

    elif btype == "heading":
        level = props.get("level", 1)
        hashes = "#" * int(level)
        lines.append(f"{prefix}{hashes} {inline}")
        lines.append("")

    elif btype == "bulletListItem":
        lines.append(f"{prefix}- {inline}")

    elif btype == "numberedListItem":
        n = counters.get(indent, 0) + 1
        counters[indent] = n
        start = props.get("start")
        if start is not None and n == 1:
            n = int(start)
            counters[indent] = n
        lines.append(f"{prefix}{n}. {inline}")

    elif btype == "checkListItem":
        checked = props.get("checked", False)
        mark = "x" if checked else " "
        lines.append(f"{prefix}- [{mark}] {inline}")

    elif btype == "toggleListItem":
        lines.append(f"{prefix}- {inline}")

    elif btype == "quote":
        for line in inline.split("\n"):
            lines.append(f"{prefix}> {line}")
        lines.append("")

    elif btype == "codeBlock":
        lang = props.get("language", "")
        lines.append(f"{prefix}```{lang}")
        # Code blocks store their text in inline content
        lines.append(f"{prefix}{inline}")
        lines.append(f"{prefix}```")
        lines.append("")

    elif btype == "divider":
        lines.append(f"{prefix}---")
        lines.append("")

    elif btype == "image":
        url = props.get("url", "")
        caption = props.get("caption", "")
        name = props.get("name", caption or "image")
        lines.append(f"{prefix}![{name}]({url})")
        if caption:
            lines.append(f"{prefix}*{caption}*")
        lines.append("")

    elif btype == "video":
        url = props.get("url", "")
        caption = props.get("caption", "")
        name = props.get("name", "video")
        lines.append(f"{prefix}[{name}]({url})")
        if caption:
            lines.append(f"{prefix}*{caption}*")
        lines.append("")

    elif btype == "audio":
        url = props.get("url", "")
        caption = props.get("caption", "")
        name = props.get("name", "audio")
        lines.append(f"{prefix}[{name}]({url})")
        if caption:
            lines.append(f"{prefix}*{caption}*")
        lines.append("")

    elif btype == "file":
        url = props.get("url", "")
        caption = props.get("caption", "")
        name = props.get("name", "file")
        lines.append(f"{prefix}[{name}]({url})")
        if caption:
            lines.append(f"{prefix}*{caption}*")
        lines.append("")

    elif btype == "chemStructure":
        _render_chem_structure(props, lines, prefix)

    elif btype == "table":
        _render_table(content, lines, prefix)

    else:
        # Unknown block type — render inline content as a paragraph
        if inline:
            lines.append(f"{prefix}{inline}")
            lines.append("")

    if children:
        _render_blocks(children, lines, indent + 1, counters)


def _render_chem_structure(props: dict, lines: list[str], prefix: str) -> None:
    """Render a chemical structure block.

    Every saved structure has an SVG preview (generated on save by
    ``KetcherModal``).  We emit it as a data-URI ``![…](data:…)`` image so
    that pandoc-based exports (HTML, PDF, DOCX) can embed the structure.
    The SMILES string (when available) is used as alt text.

    Blocks with no SVG are empty (user inserted the slash-command but never
    drew anything) and are silently skipped.
    """
    svg = props.get("svgPreview", "")
    if not svg:
        return

    smiles = props.get("smiles", "")
    alt = smiles if smiles else "chemical structure"

    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    data_uri = f"data:image/svg+xml;base64,{b64}"
    lines.append(f"{prefix}![{alt}]({data_uri})")
    lines.append("")


def _render_table(content: dict | list, lines: list[str], prefix: str) -> None:
    """Render a BlockNote table block.

    ``content`` is ``{"type": "tableContent", "rows": [...]}``.
    Each row has ``cells`` — each cell is itself a list of inline-content
    arrays (one per paragraph in the cell).
    """
    if isinstance(content, dict):
        rows = content.get("rows", [])
    elif isinstance(content, list):
        rows = content
    else:
        return

    if not rows:
        return

    rendered_rows: list[list[str]] = []
    for row in rows:
        cells = row.get("cells", [])
        rendered_cells: list[str] = []
        for cell in cells:
            # Each cell is a list of inline-content arrays
            parts: list[str] = []
            if isinstance(cell, list):
                for segment in cell:
                    if isinstance(segment, list):
                        parts.append(_render_inline(segment))
                    elif isinstance(segment, dict):
                        parts.append(_render_inline([segment]))
                    else:
                        parts.append(str(segment))
            else:
                parts.append(str(cell))
            rendered_cells.append(" ".join(parts).replace("|", "\\|"))
        rendered_rows.append(rendered_cells)

    if not rendered_rows:
        return

    # Determine column count from the widest row
    ncols = max(len(r) for r in rendered_rows)

    # Pad rows to have equal columns
    for row in rendered_rows:
        while len(row) < ncols:
            row.append("")

    # Header row
    lines.append(f"{prefix}| " + " | ".join(rendered_rows[0]) + " |")
    lines.append(f"{prefix}| " + " | ".join("---" for _ in range(ncols)) + " |")

    for row in rendered_rows[1:]:
        lines.append(f"{prefix}| " + " | ".join(row) + " |")

    lines.append("")


def _render_inline(content: list) -> str:
    """Render an array of inline content nodes to a Markdown string."""
    parts: list[str] = []
    for node in content:
        if isinstance(node, str):
            parts.append(node)
            continue
        if not isinstance(node, dict):
            continue

        ntype = node.get("type", "text")

        if ntype == "text":
            text = node.get("text", "")
            styles = node.get("styles", {})
            text = _apply_styles(text, styles)
            parts.append(text)

        elif ntype == "link":
            href = node.get("href", "")
            link_content = node.get("content", [])
            link_text = _render_inline(link_content) if link_content else href
            parts.append(f"[{link_text}]({href})")

        else:
            # Unknown inline type — try to extract text
            text = node.get("text", "")
            if text:
                parts.append(text)

    return "".join(parts)


def _apply_styles(text: str, styles: dict) -> str:
    """Wrap *text* with Markdown formatting based on BlockNote styles."""
    if not styles or not text:
        return text

    if styles.get("code"):
        return f"`{text}`"

    if styles.get("bold") and styles.get("italic"):
        text = f"***{text}***"
    elif styles.get("bold"):
        text = f"**{text}**"
    elif styles.get("italic"):
        text = f"*{text}*"

    if styles.get("strike"):
        text = f"~~{text}~~"

    if styles.get("underline"):
        # No native Markdown underline; use HTML
        text = f"<u>{text}</u>"

    return text


# ==================================================================
# Markdown → BlockNote blocks
# ==================================================================

# Line-level patterns
_RE_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_RE_BULLET = re.compile(r"^[-*+]\s+(.*)$")
_RE_NUMBERED = re.compile(r"^(\d+)\.\s+(.*)$")
_RE_CHECKLIST = re.compile(r"^[-*+]\s+\[([ xX])\]\s+(.*)$")
_RE_BLOCKQUOTE = re.compile(r"^>\s?(.*)$")
_RE_DIVIDER = re.compile(r"^(-{3,}|\*{3,}|_{3,})\s*$")
_RE_IMAGE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$")
_RE_CODE_FENCE = re.compile(r"^```(.*)$")
_RE_TABLE_ROW = re.compile(r"^\|(.+)\|\s*$")
_RE_TABLE_SEP = re.compile(r"^\|\s*[-:]+[-| :]*\|\s*$")

# Inline patterns (ordered by specificity – longest/greediest first)
_INLINE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("link", re.compile(r"\[([^\]]*)\]\(([^)]+)\)")),
    ("bold_italic", re.compile(r"\*{3}(.+?)\*{3}")),
    ("bold", re.compile(r"\*{2}(.+?)\*{2}")),
    ("italic", re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")),
    ("code", re.compile(r"`(.+?)`")),
    ("strike", re.compile(r"~~(.+?)~~")),
    ("underline", re.compile(r"<u>(.+?)</u>")),
]


def markdown_to_blocks(md: str) -> tuple[list[dict], str | None]:
    """Parse a Markdown string into BlockNote JSON blocks.

    Returns ``(blocks, title)`` where *title* is extracted from a leading
    ``# …`` heading (if present) and excluded from the block list.
    """
    lines = md.split("\n")
    # Strip trailing blank lines
    while lines and lines[-1].strip() == "":
        lines.pop()

    blocks: list[dict] = []
    title: str | None = None
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Blank line – skip
        if stripped == "":
            i += 1
            continue

        # Code fence
        m = _RE_CODE_FENCE.match(stripped)
        if m:
            lang = m.group(1).strip()
            code_lines: list[str] = []
            i += 1
            while i < len(lines):
                if lines[i].strip().startswith("```"):
                    i += 1
                    break
                code_lines.append(lines[i])
                i += 1
            blocks.append(_block(
                "codeBlock",
                props={"language": lang} if lang else {},
                content=[{"type": "text", "text": "\n".join(code_lines)}],
            ))
            continue

        # Divider
        if _RE_DIVIDER.match(stripped):
            blocks.append(_block("divider"))
            i += 1
            continue

        # Image: ![alt](url) optionally followed by *caption*
        m = _RE_IMAGE.match(stripped)
        if m:
            alt = m.group(1)
            url = m.group(2)
            caption = ""
            if i + 1 < len(lines):
                cap_match = re.match(r"^\*(.+)\*$", lines[i + 1].strip())
                if cap_match:
                    caption = cap_match.group(1)
                    i += 1
            props: dict = {"url": url}
            if alt:
                props["name"] = alt
            if caption:
                props["caption"] = caption
            blocks.append(_block("image", props=props))
            i += 1
            continue

        # Table (collect consecutive | rows)
        if _RE_TABLE_ROW.match(stripped):
            table_lines: list[str] = []
            while i < len(lines) and _RE_TABLE_ROW.match(lines[i].strip()):
                table_lines.append(lines[i].strip())
                i += 1
            blocks.append(_parse_table(table_lines))
            continue

        # Heading
        m = _RE_HEADING.match(stripped)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            # Extract first heading as document title
            if not blocks and title is None and level == 1:
                title = text
                i += 1
                continue
            blocks.append(_block("heading", props={"level": level}, content=_parse_inline(text)))
            i += 1
            continue

        # Checklist (must check before bullet)
        m = _RE_CHECKLIST.match(stripped)
        if m:
            checked = m.group(1).lower() == "x"
            text = m.group(2)
            blocks.append(_block("checkListItem", props={"checked": checked}, content=_parse_inline(text)))
            i += 1
            continue

        # Bullet list
        m = _RE_BULLET.match(stripped)
        if m:
            blocks.append(_block("bulletListItem", content=_parse_inline(m.group(1))))
            i += 1
            continue

        # Numbered list
        m = _RE_NUMBERED.match(stripped)
        if m:
            blocks.append(_block("numberedListItem", content=_parse_inline(m.group(2))))
            i += 1
            continue

        # Blockquote (collect consecutive > lines)
        m = _RE_BLOCKQUOTE.match(stripped)
        if m:
            quote_parts: list[str] = []
            while i < len(lines):
                qm = _RE_BLOCKQUOTE.match(lines[i].strip())
                if not qm:
                    break
                quote_parts.append(qm.group(1))
                i += 1
            blocks.append(_block("quote", content=_parse_inline("\n".join(quote_parts))))
            continue

        # Paragraph (default)
        blocks.append(_block("paragraph", content=_parse_inline(stripped)))
        i += 1

    return blocks, title


def _block(
    btype: str,
    *,
    props: dict | None = None,
    content: list | dict | None = None,
    children: list | None = None,
) -> dict:
    """Construct a BlockNote block dict."""
    b: dict = {"type": btype}
    if props:
        b["props"] = props
    if content is not None:
        b["content"] = content
    else:
        b["content"] = []
    b["children"] = children or []
    return b


def _parse_inline(text: str) -> list[dict]:
    """Parse inline Markdown formatting into BlockNote inline content nodes."""
    if not text:
        return []

    nodes: list[dict] = []
    pos = 0

    while pos < len(text):
        # Find the earliest match across all patterns
        best_match: re.Match[str] | None = None
        best_kind: str | None = None

        for kind, pattern in _INLINE_PATTERNS:
            m = pattern.search(text, pos)
            if m and (best_match is None or m.start() < best_match.start()):
                best_match = m
                best_kind = kind

        if best_match is None:
            remaining = text[pos:]
            if remaining:
                nodes.append({"type": "text", "text": remaining})
            break

        # Plain text before the match
        if best_match.start() > pos:
            nodes.append({"type": "text", "text": text[pos:best_match.start()]})

        if best_kind == "link":
            link_text = best_match.group(1)
            href = best_match.group(2)
            nodes.append({
                "type": "link",
                "href": href,
                "content": _parse_inline(link_text) if link_text else [],
            })
        elif best_kind == "code":
            nodes.append({"type": "text", "text": best_match.group(1), "styles": {"code": True}})
        elif best_kind == "bold_italic":
            nodes.append({"type": "text", "text": best_match.group(1), "styles": {"bold": True, "italic": True}})
        elif best_kind == "bold":
            nodes.append({"type": "text", "text": best_match.group(1), "styles": {"bold": True}})
        elif best_kind == "italic":
            nodes.append({"type": "text", "text": best_match.group(1), "styles": {"italic": True}})
        elif best_kind == "strike":
            nodes.append({"type": "text", "text": best_match.group(1), "styles": {"strike": True}})
        elif best_kind == "underline":
            nodes.append({"type": "text", "text": best_match.group(1), "styles": {"underline": True}})

        pos = best_match.end()

    return nodes


def _parse_table(lines: list[str]) -> dict:
    """Parse a sequence of ``| … |`` lines into a BlockNote table block."""
    rows: list[dict] = []
    for line in lines:
        # Skip separator rows (| --- | --- |)
        if _RE_TABLE_SEP.match(line):
            continue
        # Split cells, stripping the leading/trailing |
        raw_cells = line.strip("|").split("|")
        cells = []
        for cell in raw_cells:
            cell_text = cell.strip().replace("\\|", "|")
            cells.append([_parse_inline(cell_text)])
        rows.append({"cells": cells})

    return _block("table", content={"type": "tableContent", "rows": rows})
