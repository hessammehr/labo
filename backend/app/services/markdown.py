"""Convert BlockNote JSON blocks to Markdown."""

from __future__ import annotations


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

    elif btype == "table":
        _render_table(content, lines, prefix)

    else:
        # Unknown block type — render inline content as a paragraph
        if inline:
            lines.append(f"{prefix}{inline}")
            lines.append("")

    if children:
        _render_blocks(children, lines, indent + 1, counters)


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
