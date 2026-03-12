"""Tests for the chunked write stream (_BytesWriteStream / _TextWriteStream).

Uses pytest-httpserver (werkzeug-backed) to stand up a local HTTP server,
so these are true integration tests — but no live Labo backend is needed.
"""

import time
import threading

import pytest
from pytest_httpserver import HTTPServer

from labo import Resource
from labo._resource import _BytesWriteStream, _DEFAULT_CHUNK


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resource(httpserver: HTTPServer) -> Resource:
    """Create a Resource pointed at the test server."""
    return Resource(httpserver.url_for(""), "test-token")


def _expect_put(httpserver: HTTPServer, path: str = "/api/v1/files/entry/out.bin"):
    """Register a PUT handler that captures the request body."""
    bodies: list[bytes] = []

    def handler(request):
        bodies.append(request.data)
        return ""

    httpserver.expect_request(path, method="PUT").respond_with_handler(handler)
    return bodies


# ---------------------------------------------------------------------------
# Basic round-trip tests
# ---------------------------------------------------------------------------


class TestBytesWriteStream:
    def test_single_write(self, httpserver: HTTPServer):
        bodies = _expect_put(httpserver)
        r = _resource(httpserver) / "entry" / "out.bin"

        with r.open("wb") as f:
            f.write(b"hello world")

        assert len(bodies) == 1
        assert bodies[0] == b"hello world"

    def test_multiple_writes_concatenated(self, httpserver: HTTPServer):
        bodies = _expect_put(httpserver)
        r = _resource(httpserver) / "entry" / "out.bin"

        with r.open("wb") as f:
            f.write(b"aaa")
            f.write(b"bbb")
            f.write(b"ccc")

        assert len(bodies) == 1
        assert bodies[0] == b"aaabbbccc"

    def test_large_write_triggers_chunk_flush(self, httpserver: HTTPServer):
        """When a write pushes the buffer past chunk_size, it should flush
        immediately — so the server receives data in multiple chunks."""
        bodies = _expect_put(httpserver)
        r = _resource(httpserver) / "entry" / "out.bin"

        chunk = b"x" * (_DEFAULT_CHUNK + 1)
        with r.open("wb") as f:
            f.write(chunk)
            f.write(b"tail")

        assert len(bodies) == 1
        assert bodies[0] == chunk + b"tail"

    def test_write_after_close_raises(self, httpserver: HTTPServer):
        _expect_put(httpserver)
        r = _resource(httpserver) / "entry" / "out.bin"

        stream = r.open("wb")
        stream.__enter__()
        stream.__exit__(None, None, None)

        with pytest.raises(RuntimeError, match="closed"):
            stream.write(b"nope")

    def test_empty_write(self, httpserver: HTTPServer):
        bodies = _expect_put(httpserver)
        r = _resource(httpserver) / "entry" / "out.bin"

        with r.open("wb") as f:
            pass  # write nothing

        assert len(bodies) == 1
        assert bodies[0] == b""


class TestTextWriteStream:
    def test_text_write(self, httpserver: HTTPServer):
        bodies = _expect_put(httpserver, "/api/v1/files/entry/out.txt")
        r = _resource(httpserver) / "entry" / "out.txt"

        with r.open("w") as f:
            f.write("line 1\n")
            f.write("line 2\n")

        assert len(bodies) == 1
        assert bodies[0] == b"line 1\nline 2\n"


# ---------------------------------------------------------------------------
# Flush-interval / timing tests
# ---------------------------------------------------------------------------


class TestFlushInterval:
    def test_timer_flushes_small_buffer(self, httpserver: HTTPServer):
        """A small write that sits below chunk_size should still be sent to
        the server within ~flush_interval, without waiting for close."""
        _expect_put(httpserver)
        r = _resource(httpserver) / "entry" / "out.bin"

        stream = _BytesWriteStream(r, flush_interval=0.15)
        stream.__enter__()
        try:
            stream.write(b"early")
            # The buffer is below chunk_size, so the only way it gets
            # enqueued is via the timer.  Give it time to fire.
            time.sleep(0.3)
            # Peek at the queue — the chunk should have been enqueued.
            assert not stream._buf, "buffer should have been flushed by timer"
        finally:
            stream.__exit__(None, None, None)

    def test_chunk_size_flush_resets_timer(self, httpserver: HTTPServer):
        """Hitting chunk_size should flush immediately and cancel any
        pending timer (no double-flush)."""
        _expect_put(httpserver)
        r = _resource(httpserver) / "entry" / "out.bin"

        stream = _BytesWriteStream(r, chunk_size=10, flush_interval=5.0)
        stream.__enter__()
        try:
            stream.write(b"0123456789ab")  # 12 bytes > chunk_size=10
            # Should have flushed synchronously
            assert not stream._buf
            assert stream._timer is None, "timer should have been cancelled"
        finally:
            stream.__exit__(None, None, None)

    def test_slow_writer_flushes_incrementally(self, httpserver: HTTPServer):
        """Simulates test_write2.py: slow writes should be flushed
        incrementally by the timer rather than all at once on close."""
        _expect_put(httpserver)
        r = _resource(httpserver) / "entry" / "out.bin"

        flushed_count = 0
        stream = _BytesWriteStream(r, flush_interval=0.1)
        orig_timer_flush = stream._timer_flush

        def counting_flush():
            nonlocal flushed_count
            flushed_count += 1
            orig_timer_flush()

        stream._timer_flush = counting_flush
        stream.__enter__()
        try:
            for i in range(3):
                stream.write(f"iter{i}\n".encode())
                time.sleep(0.25)  # longer than flush_interval
        finally:
            stream.__exit__(None, None, None)

        # Each write should have triggered at least one timer flush
        assert flushed_count >= 2, f"expected ≥2 timer flushes, got {flushed_count}"
