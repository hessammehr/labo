"""MIME type helpers with deterministic cross-platform behavior."""

from __future__ import annotations

import mimetypes

# Some MIME mappings vary by OS/Python build. Register the ones we rely on.
mimetypes.add_type("text/markdown", ".md")
mimetypes.add_type("text/markdown", ".markdown")


def guess_mime(filename: str, default: str = "application/octet-stream") -> str:
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or default
