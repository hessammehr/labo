"""Export entries and notebooks to various formats via pandoc."""

from __future__ import annotations

import io
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from app.services.markdown import blocks_to_markdown

# Regex matching /api/attachments/<hex-id> URLs in markdown output
_ATTACHMENT_URL_RE = re.compile(r"/api/attachments/([0-9a-fA-F]+)")

# Supported export formats and their pandoc output format / file extension / MIME type
EXPORT_FORMATS: dict[str, dict[str, str]] = {
    "md": {
        "extension": ".md",
        "mime": "text/markdown",
    },
    "html": {
        "pandoc_to": "html",
        "extension": ".html",
        "mime": "text/html",
    },
    "pdf": {
        "pandoc_to": "pdf",
        "extension": ".pdf",
        "mime": "application/pdf",
    },
    "docx": {
        "pandoc_to": "docx",
        "extension": ".docx",
        "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    },
    "latex": {
        "pandoc_to": "latex",
        "extension": ".tex",
        "mime": "application/x-latex",
    },
    "attachments": {
        "extension": ".zip",
        "mime": "application/zip",
    },
}


# ------------------------------------------------------------------
# Attachment resolution
# ------------------------------------------------------------------

class AttachmentInfo:
    """Metadata for a single attachment needed during export."""

    __slots__ = ("id", "filename", "storage_path")

    def __init__(self, id: str, filename: str, storage_path: Path) -> None:
        self.id = id
        self.filename = filename
        self.storage_path = storage_path


def _collect_attachment_ids(markdown: str) -> set[str]:
    """Return the set of attachment IDs referenced in *markdown*."""
    return set(_ATTACHMENT_URL_RE.findall(markdown))


def _stage_attachments(
    markdown: str,
    attachments: list[AttachmentInfo],
    dest_dir: Path,
    *,
    subdir: str = "attachments",
    _referenced_ids: set[str] | None = None,
) -> str:
    """Copy referenced attachment files into *dest_dir/subdir* and rewrite
    the ``/api/attachments/<id>`` URLs to use relative paths.

    Returns the rewritten text.

    If *_referenced_ids* is provided it is used instead of scanning *markdown*
    for attachment URLs (useful when the text has already been converted to
    another format but still contains the same URL patterns).
    """
    referenced_ids = _referenced_ids if _referenced_ids is not None else _collect_attachment_ids(markdown)
    if not referenced_ids:
        return markdown

    att_dir = dest_dir / subdir
    att_dir.mkdir(parents=True, exist_ok=True)

    # Build lookup: id → AttachmentInfo
    lookup = {a.id: a for a in attachments}

    # De-duplicate target filenames within this export
    used_filenames: set[str] = set()

    def _unique_name(name: str) -> str:
        if name not in used_filenames:
            used_filenames.add(name)
            return name
        stem = Path(name).stem
        suffix = Path(name).suffix
        n = 1
        while True:
            candidate = f"{stem}_{n}{suffix}"
            if candidate not in used_filenames:
                used_filenames.add(candidate)
                return candidate
            n += 1

    id_to_relpath: dict[str, str] = {}

    for att_id in referenced_ids:
        info = lookup.get(att_id)
        if info is None or not info.storage_path.exists():
            continue
        target_name = _unique_name(info.filename)
        target_path = att_dir / target_name
        shutil.copy2(info.storage_path, target_path)
        id_to_relpath[att_id] = f"{subdir}/{target_name}"

    def _replace(m: re.Match[str]) -> str:
        att_id = m.group(1)
        return id_to_relpath.get(att_id, m.group(0))

    return _ATTACHMENT_URL_RE.sub(_replace, markdown)


# ------------------------------------------------------------------
# Markdown generation
# ------------------------------------------------------------------

def entry_to_markdown(
    content_blocks: list[dict],
    title: str,
) -> str:
    """Convert a single entry's blocks to markdown with an H1 title."""
    return blocks_to_markdown(content_blocks, title=title)


def notebook_to_markdown(
    entries: list[dict],
) -> str:
    """Concatenate multiple entries into a single markdown document.

    Each entry dict must have ``title`` and ``content_blocks`` keys.
    Each entry is separated by a horizontal rule and headed with ``# Title``.
    """
    parts: list[str] = []
    for entry in entries:
        md = blocks_to_markdown(entry["content_blocks"], title=entry["title"])
        parts.append(md)
    return "\n---\n\n".join(parts)


# ------------------------------------------------------------------
# Export helpers
# ------------------------------------------------------------------

def convert_with_pandoc(
    markdown: str,
    fmt: str,
    attachments: list[AttachmentInfo],
    *,
    standalone: bool = True,
) -> bytes:
    """Convert markdown to the requested format using pandoc.

    Attachment URLs are resolved to local files so pandoc can embed them.
    Returns raw bytes of the converted document.
    Raises ``ValueError`` for unknown formats and ``RuntimeError`` if pandoc fails.
    """
    info = EXPORT_FORMATS.get(fmt)
    if info is None:
        raise ValueError(f"Unsupported export format: {fmt}")

    pandoc_to = info["pandoc_to"]

    with tempfile.TemporaryDirectory() as tmpdir:
        work = Path(tmpdir)
        resolved_md = _stage_attachments(markdown, attachments, work)

        cmd = ["pandoc", "-f", "markdown", "-t", pandoc_to]
        if standalone and fmt != "pdf":
            cmd.append("-s")
        cmd.extend(["--resource-path", str(work)])

        if fmt == "pdf":
            outpath = work / "output.pdf"
            cmd.extend(["-o", str(outpath)])
            proc = subprocess.run(
                cmd,
                input=resolved_md.encode("utf-8"),
                capture_output=True,
                timeout=120,
                cwd=str(work),
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    f"pandoc failed (exit {proc.returncode}): "
                    f"{proc.stderr.decode(errors='replace')}"
                )
            return outpath.read_bytes()

        if fmt in ("docx",):
            outpath = work / f"output{info['extension']}"
            cmd.extend(["-o", str(outpath)])
            proc = subprocess.run(
                cmd,
                input=resolved_md.encode("utf-8"),
                capture_output=True,
                timeout=120,
                cwd=str(work),
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    f"pandoc failed (exit {proc.returncode}): "
                    f"{proc.stderr.decode(errors='replace')}"
                )
            return outpath.read_bytes()

        # Text-based formats (html, latex): read from stdout
        proc = subprocess.run(
            cmd,
            input=resolved_md.encode("utf-8"),
            capture_output=True,
            timeout=120,
            cwd=str(work),
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"pandoc failed (exit {proc.returncode}): "
                f"{proc.stderr.decode(errors='replace')}"
            )
        return proc.stdout


def _zip_directory(work: Path) -> bytes:
    """Zip all files under *work*, rooted at ``work.parent``."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fpath in sorted(work.rglob("*")):
            if fpath.is_file():
                zf.write(fpath, fpath.relative_to(work.parent))
    return buf.getvalue()


def export_text_zip(
    text: str,
    filename: str,
    basename: str,
    attachments: list[AttachmentInfo],
    markdown_for_refs: str,
) -> bytes:
    """Bundle a text file + referenced attachments into a zip archive.

    *text* is the document content (markdown or LaTeX).
    *filename* is the name of the main file inside the zip (e.g. ``foo.md``).
    *markdown_for_refs* is the original markdown used to discover attachment
    references (may differ from *text* when *text* is pandoc-converted LaTeX).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        work = Path(tmpdir) / basename
        work.mkdir()

        # Stage attachments using the original markdown URLs, then apply the
        # same URL rewrites to the output text.
        resolved = _stage_attachments(text, attachments, work,
                                      _referenced_ids=_collect_attachment_ids(markdown_for_refs))
        (work / filename).write_text(resolved, encoding="utf-8")
        return _zip_directory(work)


def export_attachments_zip(
    attachments: list[AttachmentInfo],
    basename: str,
) -> bytes:
    """Create a zip containing only the attachment files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        work = Path(tmpdir) / basename
        att_dir = work / "attachments"
        att_dir.mkdir(parents=True)

        used: set[str] = set()
        for att in attachments:
            if not att.storage_path.exists():
                continue
            name = att.filename
            if name in used:
                stem = Path(name).stem
                suffix = Path(name).suffix
                n = 1
                while f"{stem}_{n}{suffix}" in used:
                    n += 1
                name = f"{stem}_{n}{suffix}"
            used.add(name)
            shutil.copy2(att.storage_path, att_dir / name)

        return _zip_directory(work)


def export_document(
    markdown: str,
    fmt: str,
    basename: str,
    attachments: list[AttachmentInfo],
) -> tuple[bytes, bool]:
    """High-level export: returns ``(data, is_zip)`` for any supported format.

    For ``md`` and ``latex``, returns a zip archive when the markdown
    references attachments, or the plain file when there are none.
    For ``attachments``, always returns a zip of the raw attachment files.
    For other formats, delegates to pandoc (``is_zip`` is always ``False``).
    """
    if fmt == "attachments":
        return export_attachments_zip(attachments, basename), True

    has_refs = bool(_collect_attachment_ids(markdown) & {a.id for a in attachments})

    if fmt == "md":
        if has_refs:
            return export_text_zip(
                markdown, f"{basename}.md", basename, attachments, markdown,
            ), True
        return markdown.encode("utf-8"), False

    if fmt == "latex":
        latex_bytes = convert_with_pandoc(markdown, fmt, attachments)
        if has_refs:
            latex_text = latex_bytes.decode("utf-8")
            return export_text_zip(
                latex_text, f"{basename}.tex", basename, attachments, markdown,
            ), True
        return latex_bytes, False

    return convert_with_pandoc(markdown, fmt, attachments), False
