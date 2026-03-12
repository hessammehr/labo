"""Tests for the export service."""

import base64
from pathlib import Path
import shutil
import struct
import tempfile

import pytest
from PIL import Image

from app.services.export import (
    AttachmentInfo,
    _stage_attachments,
    convert_with_pandoc,
    export_attachments_zip,
)


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


_need_pandoc = pytest.mark.skipif(
    shutil.which("pandoc") is None,
    reason="pandoc not installed",
)


@_need_pandoc
class TestHtmlEmbedResources:
    """HTML export should embed images as data URIs, not external file refs."""

    def test_png_embedded_as_data_uri(self, tmp_path: Path):
        """A referenced PNG should appear as a base64 data URI in the HTML."""
        # Create a real 1×1 red PNG with Pillow
        png_path = tmp_path / "dot.png"
        Image.new("RGB", (1, 1), "red").save(str(png_path), "PNG")

        att = AttachmentInfo(id="aa0011", filename="dot.png", storage_path=png_path)
        md = "![red dot](/api/attachments/aa0011)"

        html = convert_with_pandoc(md, "html", [att]).decode("utf-8")

        assert "data:image/png;base64," in html
        # The relative file path should NOT appear – everything is inlined
        assert "attachments/dot.png" not in html

    def test_svg_embedded_as_data_uri(self, tmp_path: Path):
        """A referenced SVG should be inlined in the HTML export."""
        svg_path = tmp_path / "circle.svg"
        svg_path.write_text(SIMPLE_SVG)

        att = AttachmentInfo(id="bb2233", filename="circle.svg", storage_path=svg_path)
        md = "![circle](/api/attachments/bb2233)"

        html = convert_with_pandoc(md, "html", [att]).decode("utf-8")

        # SVG should be inlined as a data URI
        assert "data:image/svg+xml" in html
        assert "attachments/circle.svg" not in html


class TestEntryTitleNamespacing:
    """Notebook exports namespace attachments by entry title to avoid clashes."""

    def test_same_filename_different_entries(self, tmp_path: Path):
        """Two entries with identically-named attachments get separate dirs."""
        img1 = tmp_path / "img1.png"
        img2 = tmp_path / "img2.png"
        img1.write_bytes(b"\x89PNG entry1")
        img2.write_bytes(b"\x89PNG entry2")

        att1 = AttachmentInfo(
            id="aa0001", filename="figure.png", storage_path=img1,
            entry_title="Synthesis",
        )
        att2 = AttachmentInfo(
            id="aa0002", filename="figure.png", storage_path=img2,
            entry_title="Analysis",
        )

        md = (
            "![fig1](/api/attachments/aa0001)\n"
            "![fig2](/api/attachments/aa0002)"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            result = _stage_attachments(md, [att1, att2], dest)

            assert (dest / "attachments" / "Synthesis" / "figure.png").exists()
            assert (dest / "attachments" / "Analysis" / "figure.png").exists()
            assert "attachments/Synthesis/figure.png" in result
            assert "attachments/Analysis/figure.png" in result

            # Files have distinct content
            content1 = (dest / "attachments" / "Synthesis" / "figure.png").read_bytes()
            content2 = (dest / "attachments" / "Analysis" / "figure.png").read_bytes()
            assert content1 != content2

    def test_no_entry_title_stays_flat(self, tmp_path: Path):
        """Single-entry exports (no entry_title) use a flat attachments dir."""
        img = tmp_path / "photo.png"
        img.write_bytes(b"\x89PNG data")

        att = AttachmentInfo(id="bb0001", filename="photo.png", storage_path=img)
        md = "![photo](/api/attachments/bb0001)"

        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            result = _stage_attachments(md, [att], dest)

            assert (dest / "attachments" / "photo.png").exists()
            assert "attachments/photo.png" in result

    def test_attachments_zip_namespaced(self, tmp_path: Path):
        """export_attachments_zip namespaces by entry title."""
        f1 = tmp_path / "data1.csv"
        f2 = tmp_path / "data2.csv"
        f1.write_text("a,b\n1,2")
        f2.write_text("x,y\n3,4")

        atts = [
            AttachmentInfo(
                id="cc0001", filename="data.csv", storage_path=f1,
                entry_title="Experiment 1",
            ),
            AttachmentInfo(
                id="cc0002", filename="data.csv", storage_path=f2,
                entry_title="Experiment 2",
            ),
        ]

        import io
        import zipfile

        data = export_attachments_zip(atts, "notebook")
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = set(zf.namelist())
            assert "notebook/attachments/Experiment 1/data.csv" in names
            assert "notebook/attachments/Experiment 2/data.csv" in names
