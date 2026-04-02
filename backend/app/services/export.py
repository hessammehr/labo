"""Export entries and notebooks to various formats via pandoc."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from svglib.svglib import svg2rlg
from reportlab.graphics import renderPDF
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

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

    __slots__ = ("id", "filename", "storage_path", "entry_title")

    def __init__(
        self,
        id: str,
        filename: str,
        storage_path: Path,
        entry_title: str | None = None,
    ) -> None:
        self.id = id
        self.filename = filename
        self.storage_path = storage_path
        self.entry_title = entry_title


def collect_attachment_ids(markdown: str) -> set[str]:
    """Return the set of attachment IDs referenced in *markdown*."""
    return set(_ATTACHMENT_URL_RE.findall(markdown))


_EXIF_TRANSPOSE_EXTENSIONS = {".jpg", ".jpeg", ".tif", ".tiff", ".png", ".webp"}


def _apply_exif_transpose(path: Path) -> None:
    """Rotate an image file in-place according to its EXIF orientation tag.

    After this call the pixel data matches the intended display orientation and
    the EXIF orientation tag (if any) is reset.  This is a no-op for images
    without an orientation tag or for non-image files.
    """
    if path.suffix.lower() not in _EXIF_TRANSPOSE_EXTENSIONS:
        return
    try:
        with Image.open(path) as img:
            transposed = ImageOps.exif_transpose(img)
            if transposed is not img:
                transposed.save(path)
    except Exception:
        logger.debug("EXIF transpose skipped for %s", path, exc_info=True)


def _convert_svg_to_pdf(src: Path, dest: Path) -> None:
    """Convert an SVG file to PDF using svglib + reportlab."""
    drawing = svg2rlg(str(src))
    if drawing is None:
        raise RuntimeError(f"svglib failed to parse {src}")
    renderPDF.drawToFile(drawing, str(dest))


def _stage_attachments(
    markdown: str,
    attachments: list[AttachmentInfo],
    dest_dir: Path,
    *,
    subdir: str = "attachments",
    _referenced_ids: set[str] | None = None,
    convert_svg: bool = False,
) -> str:
    """Copy referenced attachment files into *dest_dir/subdir* and rewrite
    the ``/api/attachments/<id>`` URLs to use relative paths.

    Returns the rewritten text.

    When an attachment has ``entry_title`` set, it is placed under
    ``subdir/<entry_title>/`` to avoid filename clashes across entries in
    notebook exports.

    If *_referenced_ids* is provided it is used instead of scanning *markdown*
    for attachment URLs (useful when the text has already been converted to
    another format but still contains the same URL patterns).

    When *convert_svg* is ``True``, any ``.svg`` attachments are converted to
    PDF via svglib/reportlab so that pdflatex can embed them.
    """
    referenced_ids = _referenced_ids if _referenced_ids is not None else collect_attachment_ids(markdown)
    if not referenced_ids:
        return markdown

    # Build lookup: id → AttachmentInfo
    lookup = {a.id: a for a in attachments}

    id_to_relpath: dict[str, str] = {}

    for att_id in referenced_ids:
        info = lookup.get(att_id)
        if info is None or not info.storage_path.exists():
            continue

        # Namespace by entry title when set (notebook exports) to avoid
        # filename clashes across entries.
        if info.entry_title:
            att_dir = dest_dir / subdir / info.entry_title
        else:
            att_dir = dest_dir / subdir
        att_dir.mkdir(parents=True, exist_ok=True)

        target_name = info.filename

        # Convert SVG → PDF when targeting a LaTeX-based output format
        if convert_svg and Path(target_name).suffix.lower() == ".svg":
            pdf_name = Path(target_name).with_suffix(".pdf").name
            target_path = att_dir / pdf_name
            _convert_svg_to_pdf(info.storage_path, target_path)
            id_to_relpath[att_id] = str(target_path.relative_to(dest_dir))
        else:
            target_path = att_dir / target_name
            shutil.copy2(info.storage_path, target_path)
            _apply_exif_transpose(target_path)
            id_to_relpath[att_id] = str(target_path.relative_to(dest_dir))

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

_DATA_URI_RE = re.compile(
    r"!\[([^\]]*)\]\(data:image/svg\+xml;base64,([A-Za-z0-9+/=\s]+)\)"
)


def _materialise_data_uris(
    markdown: str,
    dest_dir: Path,
    *,
    convert_svg: bool = False,
) -> str:
    """Extract inline ``data:image/svg+xml;base64,…`` images to files.

    Each unique data URI is written to *dest_dir* as either an ``.svg`` or
    (when *convert_svg* is ``True``) a ``.pdf`` file.  The markdown is
    rewritten to reference the local file path.

    This is necessary because pandoc/pdflatex cannot consume data-URI SVGs
    directly — pdflatex shells out to ``rsvg-convert`` which expects real
    files.
    """
    img_dir = dest_dir / "chem_images"

    def _replace(m: re.Match[str]) -> str:
        alt = m.group(1)
        b64 = m.group(2).strip()
        # Deterministic filename from content hash
        digest = hashlib.sha256(b64.encode("ascii")).hexdigest()[:16]
        svg_bytes = base64.b64decode(b64)

        img_dir.mkdir(parents=True, exist_ok=True)

        if convert_svg:
            pdf_path = img_dir / f"{digest}.pdf"
            svg_path = img_dir / f"{digest}.svg"
            if not pdf_path.exists():
                svg_path.write_bytes(svg_bytes)
                _convert_svg_to_pdf(svg_path, pdf_path)
                svg_path.unlink(missing_ok=True)
            return f"![{alt}]({pdf_path})"
        else:
            svg_path = img_dir / f"{digest}.svg"
            if not svg_path.exists():
                svg_path.write_bytes(svg_bytes)
            return f"![{alt}]({svg_path})"

    return _DATA_URI_RE.sub(_replace, markdown)


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
        resolved_md = _stage_attachments(
            markdown, attachments, work,
            convert_svg=(fmt == "pdf"),
        )
        # Extract inline SVG data URIs to real files so pandoc can process them.
        # For PDF we convert to PDF via svglib/reportlab (pdflatex can't handle SVG);
        # for all other formats we keep SVG files (pandoc handles them fine).
        resolved_md = _materialise_data_uris(
            resolved_md, work, convert_svg=(fmt == "pdf"),
        )

        cmd = ["pandoc", "-f", "markdown", "-t", pandoc_to]
        if standalone and fmt != "pdf":
            cmd.append("-s")
        if fmt == "html":
            # Embed images as base64 data URIs so the HTML is self-contained.
            cmd.append("--embed-resources")
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
                                      _referenced_ids=collect_attachment_ids(markdown_for_refs))
        (work / filename).write_text(resolved, encoding="utf-8")
        return _zip_directory(work)


def export_attachments_zip(
    attachments: list[AttachmentInfo],
    basename: str,
) -> bytes:
    """Create a zip containing only the attachment files.

    When attachments carry an ``entry_title``, files are placed under
    ``attachments/<entry_title>/`` to avoid clashes across entries.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        work = Path(tmpdir) / basename

        for att in attachments:
            if not att.storage_path.exists():
                continue
            if att.entry_title:
                att_dir = work / "attachments" / att.entry_title
            else:
                att_dir = work / "attachments"
            att_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(att.storage_path, att_dir / att.filename)

        return _zip_directory(work)


# ------------------------------------------------------------------
# Labo Archive (.zip) — native-format export/import
# ------------------------------------------------------------------

#: Archive format version written into every manifest.
LABO_ARCHIVE_VERSION = 1


def _rewrite_attachment_urls(blocks: list[dict], id_map: dict[str, str]) -> list[dict]:
    """Replace ``/api/attachments/<old_id>`` with ``/api/attachments/<new_id>``
    throughout a serialised blocks structure.
    """
    if not id_map:
        return blocks
    text = json.dumps(blocks)
    for old_id, new_id in id_map.items():
        text = text.replace(f"/api/attachments/{old_id}", f"/api/attachments/{new_id}")
    return json.loads(text)


def export_labo_archive_entry(
    title: str,
    content_blocks: list[dict],
    tags: list[str],
    created_at: str,
    updated_at: str,
    attachments: list[dict],
) -> bytes:
    """Build a Labo Archive zip for a single entry.

    *attachments* is a list of dicts with keys:
    ``id``, ``filename``, ``mime_type``, ``type``, ``storage_path``.
    """
    manifest = {
        "version": LABO_ARCHIVE_VERSION,
        "kind": "entry",
        "title": title,
        "tags": tags,
        "created_at": created_at,
        "updated_at": updated_at,
        "content_blocks": content_blocks,
        "attachments": [
            {"id": a["id"], "filename": a["filename"],
             "mime_type": a["mime_type"], "type": a["type"]}
            for a in attachments
        ],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        for att in attachments:
            path = Path(att["storage_path"])
            if path.exists():
                zf.write(path, f"attachments/{att['id']}/{att['filename']}")
    return buf.getvalue()


def export_labo_archive_notebook(
    notebook_title: str,
    notebook_description: str,
    notebook_created_at: str,
    notebook_updated_at: str,
    entries: list[dict],
) -> bytes:
    """Build a Labo Archive zip for an entire notebook.

    Each item in *entries* is a dict with keys:
    ``title``, ``tags``, ``created_at``, ``updated_at``,
    ``content_blocks``, and ``attachments`` (same shape as above).
    """
    manifest = {
        "version": LABO_ARCHIVE_VERSION,
        "kind": "notebook",
        "title": notebook_title,
        "description": notebook_description,
        "created_at": notebook_created_at,
        "updated_at": notebook_updated_at,
        "entries": [
            {
                "title": e["title"],
                "tags": e["tags"],
                "created_at": e["created_at"],
                "updated_at": e["updated_at"],
                "content_blocks": e["content_blocks"],
                "attachments": [
                    {"id": a["id"], "filename": a["filename"],
                     "mime_type": a["mime_type"], "type": a["type"]}
                    for a in e.get("attachments", [])
                ],
            }
            for e in entries
        ],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        for e in entries:
            for att in e.get("attachments", []):
                path = Path(att["storage_path"])
                if path.exists():
                    zf.write(path, f"attachments/{att['id']}/{att['filename']}")
    return buf.getvalue()


def read_labo_archive(zip_bytes: bytes) -> dict:
    """Parse a Labo Archive and return its contents.

    Returns a dict::

        {
            "manifest": { ... },          # parsed manifest.json
            "files": {                    # attachment file data keyed by old ID
                "<old_id>": {
                    "filename": "...",
                    "data": b"...",
                },
                ...
            },
        }

    Raises ``ValueError`` for archives that are missing ``manifest.json`` or
    carry an unrecognised ``version`` number.
    """
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        if "manifest.json" not in zf.namelist():
            raise ValueError("Not a Labo Archive: missing manifest.json")
        manifest = json.loads(zf.read("manifest.json"))

        if manifest.get("version") != LABO_ARCHIVE_VERSION:
            raise ValueError(
                f"Unsupported Labo Archive version: {manifest.get('version')!r}"
            )

        files: dict[str, dict] = {}
        for name in zf.namelist():
            # Expected format: attachments/<old_id>/<filename>
            if not name.startswith("attachments/") or name.endswith("/"):
                continue
            parts = name.split("/", 2)  # ["attachments", "<id>", "<filename>"]
            if len(parts) != 3:
                continue
            _, old_id, filename = parts
            files[old_id] = {"filename": filename, "data": zf.read(name)}

    return {"manifest": manifest, "files": files}


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

    has_refs = bool(collect_attachment_ids(markdown) & {a.id for a in attachments})

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
