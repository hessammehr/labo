"""Tests for the export service, focusing on SVG → PDF conversion."""

from pathlib import Path
import tempfile

import pytest

from app.services.export import AttachmentInfo, _stage_attachments


SIMPLE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
    '<circle cx="50" cy="50" r="40" fill="red"/>'
    "</svg>"
)


@pytest.fixture()
def svg_attachment(tmp_path: Path) -> AttachmentInfo:
    """Create a temporary SVG file and return an AttachmentInfo for it."""
    svg_path = tmp_path / "circle.svg"
    svg_path.write_text(SIMPLE_SVG)
    return AttachmentInfo(id="aabb00", filename="circle.svg", storage_path=svg_path)


class TestSvgConversion:
    def test_svg_converted_to_pdf_when_flag_set(self, svg_attachment: AttachmentInfo):
        md = "![diagram](/api/attachments/aabb00)"
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            result = _stage_attachments(
                md, [svg_attachment], dest, convert_svg=True,
            )
            # The rewritten path should reference a .pdf, not .svg
            assert "circle.pdf" in result
            assert "circle.svg" not in result
            # The converted PDF file should exist on disk
            pdf_path = dest / "attachments" / "circle.pdf"
            assert pdf_path.exists()
            # Sanity-check: file starts with the PDF magic bytes
            assert pdf_path.read_bytes()[:5] == b"%PDF-"

    def test_svg_not_converted_when_flag_unset(self, svg_attachment: AttachmentInfo):
        md = "![diagram](/api/attachments/aabb00)"
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            result = _stage_attachments(
                md, [svg_attachment], dest, convert_svg=False,
            )
            assert "circle.svg" in result
            assert "circle.pdf" not in result
            assert (dest / "attachments" / "circle.svg").exists()

    def test_non_svg_unaffected_by_convert_flag(self, tmp_path: Path):
        png_path = tmp_path / "photo.png"
        png_path.write_bytes(b"\x89PNG fake")
        att = AttachmentInfo(id="cc1122", filename="photo.png", storage_path=png_path)
        md = "![photo](/api/attachments/cc1122)"
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            result = _stage_attachments(md, [att], dest, convert_svg=True)
            assert "photo.png" in result
            assert (dest / "attachments" / "photo.png").exists()
