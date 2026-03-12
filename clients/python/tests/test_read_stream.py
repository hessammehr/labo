"""Tests for the read stream (_BytesReadStream / _TextReadStream)."""

from pytest_httpserver import HTTPServer

from labo import Resource


def _resource(httpserver: HTTPServer) -> Resource:
    return Resource(httpserver.url_for(""), "test-token")


class TestBytesReadStream:
    def test_read_all(self, httpserver: HTTPServer):
        httpserver.expect_request("/api/v1/files/e/f.bin", method="GET").respond_with_data(
            b"hello world", content_type="application/octet-stream"
        )
        r = _resource(httpserver) / "e" / "f.bin"
        with r.open("rb") as f:
            assert f.read() == b"hello world"

    def test_read_n_bytes(self, httpserver: HTTPServer):
        httpserver.expect_request("/api/v1/files/e/f.bin", method="GET").respond_with_data(
            b"abcdefghij", content_type="application/octet-stream"
        )
        r = _resource(httpserver) / "e" / "f.bin"
        with r.open("rb") as f:
            assert f.read(3) == b"abc"
            assert f.read(4) == b"defg"
            assert f.read(100) == b"hij"  # less than 100 remaining

    def test_read_after_exhaustion_returns_empty(self, httpserver: HTTPServer):
        httpserver.expect_request("/api/v1/files/e/f.bin", method="GET").respond_with_data(
            b"short", content_type="application/octet-stream"
        )
        r = _resource(httpserver) / "e" / "f.bin"
        with r.open("rb") as f:
            assert f.read() == b"short"
            assert f.read() == b""
            assert f.read(10) == b""

    def test_sequential_small_reads_preserve_data(self, httpserver: HTTPServer):
        """Regression: old code discarded leftover bytes from each chunk."""
        data = b"0123456789" * 100  # 1000 bytes
        httpserver.expect_request("/api/v1/files/e/f.bin", method="GET").respond_with_data(
            data, content_type="application/octet-stream"
        )
        r = _resource(httpserver) / "e" / "f.bin"
        with r.open("rb") as f:
            collected = bytearray()
            while True:
                chunk = f.read(7)  # odd size to split across boundaries
                if not chunk:
                    break
                collected.extend(chunk)
            assert bytes(collected) == data


class TestTextReadStream:
    def test_read_text(self, httpserver: HTTPServer):
        httpserver.expect_request("/api/v1/files/e/f.txt", method="GET").respond_with_data(
            "héllo wörld".encode("utf-8"), content_type="text/plain"
        )
        r = _resource(httpserver) / "e" / "f.txt"
        with r.open("r") as f:
            assert f.read() == "héllo wörld"
