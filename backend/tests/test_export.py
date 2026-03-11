"""Tests for the export service, focusing on SVG → PDF conversion and EXIF handling."""

from pathlib import Path
import struct
import tempfile

import pytest
from PIL import Image

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


def _make_jpeg_with_exif_orientation(path: Path, orientation: int) -> None:
    """Create a 100×50 red JPEG with the given EXIF Orientation tag.

    The raw pixel dimensions are 100 wide × 50 tall.  An orientation of 6
    (``Rotate 270 CW``) means the image should be displayed as 50 wide × 100
    tall (i.e. portrait).
    """
    img = Image.new("RGB", (100, 50), "red")
    from PIL.ExifTags import Base as ExifTag
    import piexif

    # Build minimal EXIF with the orientation tag
    exif_dict = {"0th": {piexif.ImageIFD.Orientation: orientation}}
    exif_bytes = piexif.dump(exif_dict)
    img.save(str(path), "JPEG", exif=exif_bytes)


def _make_jpeg_with_pillow_exif(path: Path, orientation: int) -> None:
    """Create a 100×50 red JPEG with EXIF Orientation using only Pillow."""
    img = Image.new("RGB", (100, 50), "red")
    exif = img.getexif()
    # 0x0112 is the EXIF Orientation tag
    exif[0x0112] = orientation
    img.save(str(path), "JPEG", exif=exif.tobytes())


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


class TestExifTranspose:
    """Verify that EXIF orientation is baked into pixel data during staging."""

    def test_rotated_jpeg_is_transposed(self, tmp_path: Path):
        """A 100×50 JPEG with EXIF orientation 6 (90° CW) should become 50×100."""
        jpeg_path = tmp_path / "photo.jpg"
        _make_jpeg_with_pillow_exif(jpeg_path, orientation=6)

        att = AttachmentInfo(id="dd3344", filename="photo.jpg", storage_path=jpeg_path)
        md = "![photo](/api/attachments/dd3344)"

        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            _stage_attachments(md, [att], dest)

            staged = dest / "attachments" / "photo.jpg"
            assert staged.exists()
            with Image.open(staged) as img:
                w, h = img.size
                # After transpose: the 100×50 image rotated 90° becomes 50×100
                assert w == 50 and h == 100, f"Expected 50×100, got {w}×{h}"
                # Orientation tag should be absent or 1 (normal)
                exif = img.getexif()
                assert exif.get(0x0112, 1) == 1

    def test_normal_jpeg_unchanged(self, tmp_path: Path):
        """A JPEG with orientation 1 (normal) should keep its dimensions."""
        jpeg_path = tmp_path / "normal.jpg"
        _make_jpeg_with_pillow_exif(jpeg_path, orientation=1)

        att = AttachmentInfo(id="ee5566", filename="normal.jpg", storage_path=jpeg_path)
        md = "![pic](/api/attachments/ee5566)"

        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            _stage_attachments(md, [att], dest)

            staged = dest / "attachments" / "normal.jpg"
            with Image.open(staged) as img:
                w, h = img.size
                assert w == 100 and h == 50

    def test_non_image_file_not_affected(self, tmp_path: Path):
        """A .txt file should pass through staging untouched."""
        txt_path = tmp_path / "notes.txt"
        txt_path.write_text("hello world")

        att = AttachmentInfo(id="ff7788", filename="notes.txt", storage_path=txt_path)
        md = "![notes](/api/attachments/ff7788)"

        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            _stage_attachments(md, [att], dest)

            staged = dest / "attachments" / "notes.txt"
            assert staged.read_text() == "hello world"
