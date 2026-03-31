"""Pathlib-style remote resource for Labo API."""

from __future__ import annotations

import io
import queue
import threading
from contextlib import contextmanager
from os import PathLike
from typing import IO, Generator, Iterator, Literal, overload

import httpx

_DEFAULT_CHUNK = 64 * 1024  # 64 KB


class Resource(PathLike):
    """A pathlib-like handle to a remote Labo resource (notebook, entry, or file).

    Usage::

        r = Resource("https://my-labo.example.com", "labo_abc123...")

        # Navigate with /
        entry = r / "Experiment 1"
        file  = entry / "data.csv"

        # Read
        text = file.read_text()
        raw  = file.read_bytes()

        # Write
        file.write_text("col1,col2\\n1,2\\n")
        file.write_bytes(b"\\x89PNG...")

        # Streaming
        with file.open("rb") as f:
            for chunk in f:
                process(chunk)

        with (entry / "output.csv").open("w") as f:
            f.write("header\\n")
            f.write("row1\\n")

        # Listing
        for child in r.iterdir():
            print(child.name, child.is_dir())
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        _path: str = "",
        _client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._path = _path.strip("/")
        self._client = _client

    # -- Client management ---------------------------------------------------

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self._base_url,
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=httpx.Timeout(30.0, read=300.0),
            )
        return self._client

    def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> Resource:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- Path operations -----------------------------------------------------

    def __truediv__(self, other: str) -> Resource:
        new_path = f"{self._path}/{other}".strip("/") if self._path else other.strip("/")
        return Resource(
            self._base_url,
            self._token,
            _path=new_path,
            _client=self._client,
        )

    def __fspath__(self) -> str:
        return self._path

    def __repr__(self) -> str:
        return f"Resource({self._base_url!r}, path={self._path!r})"

    def __str__(self) -> str:
        return self._path or "/"

    @property
    def name(self) -> str:
        """The final component of the path."""
        return self._path.rsplit("/", 1)[-1] if self._path else ""

    @property
    def parent(self) -> Resource:
        """The parent resource."""
        if "/" in self._path:
            parent_path = self._path.rsplit("/", 1)[0]
        else:
            parent_path = ""
        return Resource(
            self._base_url,
            self._token,
            _path=parent_path,
            _client=self._client,
        )

    @property
    def parts(self) -> tuple[str, ...]:
        """The path split into components."""
        return tuple(self._path.split("/")) if self._path else ()

    @property
    def suffix(self) -> str:
        """The file extension (e.g. '.csv')."""
        name = self.name
        if "." in name:
            return "." + name.rsplit(".", 1)[1]
        return ""

    @property
    def stem(self) -> str:
        """The filename without the final extension."""
        name = self.name
        if "." in name:
            return name.rsplit(".", 1)[0]
        return name

    # -- API URL helper ------------------------------------------------------

    @property
    def _url(self) -> str:
        return f"/api/v1/files/{self._path}" if self._path else "/api/v1/files/"

    # -- Entry content access ------------------------------------------------

    def read_markdown(self) -> str:
        """Read the entry's text content as Markdown.

        Only works when this resource points to an entry (not a file).
        """
        resp = self._get_client().get(self._url, params={"content": "markdown"})
        resp.raise_for_status()
        return resp.text

    def read_blocks(self) -> list[dict]:
        """Read the entry's text content as BlockNote JSON blocks.

        Only works when this resource points to an entry (not a file).
        """
        resp = self._get_client().get(self._url, params={"content": "blocks"})
        resp.raise_for_status()
        return resp.json()["blocks"]

    def write_blocks(self, blocks: list[dict], expected_version: int | None = None) -> None:
        """Write the entry's text content as BlockNote JSON blocks.

        Only works when this resource points to an entry (not a file).

        If ``expected_version`` is provided, the server rejects stale writes
        with HTTP 409.
        """
        import json

        payload: dict[str, object] = {"blocks": blocks}
        if expected_version is not None:
            payload["expected_version"] = expected_version

        resp = self._get_client().put(
            self._url,
            content=json.dumps(payload).encode("utf-8"),
            params={"content": "blocks"},
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()

    # -- Rename / move -------------------------------------------------------

    def rename(self, target: str) -> Resource:
        """Rename or move this entry or file. Returns a new Resource.

        *target* is a path relative to the token root, matching
        ``pathlib.Path.rename()`` semantics::

            # Rename entry
            entry = entry.rename("New Title")

            # Rename file in place
            f = f.rename("Entry/new_name.csv")

            # Move file to another entry
            f = f.rename("Other Entry/data.csv")
        """
        import json

        resp = self._get_client().patch(
            self._url,
            content=json.dumps({"target": target}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        new_path = resp.json()["path"]
        return Resource(
            self._base_url,
            self._token,
            _path=new_path,
            _client=self._client,
        )

    # -- Existence check -----------------------------------------------------

    def exists(self) -> bool:
        """Return True if this resource exists on the server."""
        resp = self._get_client().head(self._url)
        if resp.status_code == 404:
            return False
        resp.raise_for_status()
        return True

    # -- Read operations -----------------------------------------------------

    def read_bytes(self) -> bytes:
        """Read the entire file as bytes."""
        resp = self._get_client().get(self._url)
        resp.raise_for_status()
        return resp.content

    def read_text(self, encoding: str = "utf-8") -> str:
        """Read the entire file as a string."""
        return self.read_bytes().decode(encoding)

    def iter_bytes(self, chunk_size: int = _DEFAULT_CHUNK) -> Generator[bytes, None, None]:
        """Stream file contents as byte chunks."""
        with self._get_client().stream("GET", self._url) as resp:
            resp.raise_for_status()
            yield from resp.iter_bytes(chunk_size)

    # -- Write operations ----------------------------------------------------

    def write_bytes(self, data: bytes, *, content_type: str = "application/octet-stream") -> dict:
        """Write bytes to the file (create or overwrite)."""
        resp = self._get_client().put(
            self._url,
            content=data,
            headers={"Content-Type": content_type},
        )
        resp.raise_for_status()
        return resp.json()

    def write_text(
        self, data: str, encoding: str = "utf-8", *, content_type: str = "text/plain"
    ) -> dict:
        """Write a string to the file (create or overwrite)."""
        return self.write_bytes(data.encode(encoding), content_type=content_type)

    # -- Streaming open() ---------------------------------------------------

    @overload
    def open(self, mode: Literal["r"], encoding: str = "utf-8") -> _TextReadStream: ...
    @overload
    def open(self, mode: Literal["rb"]) -> _BytesReadStream: ...
    @overload
    def open(self, mode: Literal["w"], encoding: str = "utf-8") -> _TextWriteStream: ...
    @overload
    def open(self, mode: Literal["wb"]) -> _BytesWriteStream: ...

    def open(
        self,
        mode: str = "r",
        encoding: str = "utf-8",
    ) -> _TextReadStream | _BytesReadStream | _TextWriteStream | _BytesWriteStream:
        """Open the resource for streaming reading or writing.

        Modes:
            ``"r"``  — streaming text read
            ``"rb"`` — streaming binary read
            ``"w"``  — buffered text write (uploads on close)
            ``"wb"`` — streaming binary write (chunked transfer encoding)
        """
        if mode == "r":
            return _TextReadStream(self, encoding)
        elif mode == "rb":
            return _BytesReadStream(self)
        elif mode == "w":
            return _TextWriteStream(self, encoding)
        elif mode == "wb":
            return _BytesWriteStream(self)
        else:
            raise ValueError(f"Unsupported mode: {mode!r}. Use 'r', 'rb', 'w', or 'wb'.")

    # -- Directory operations ------------------------------------------------

    def iterdir(self) -> Iterator[_DirEntry]:
        """List children of this resource (entries in a notebook, or files in an entry)."""
        resp = self._get_client().get(self._url)
        resp.raise_for_status()
        items = resp.json()
        for item in items:
            child = self / item["name"]
            yield _DirEntry(
                resource=child,
                entry_type=item.get("type", "file"),
                size=item.get("size"),
                mime_type=item.get("mime_type"),
            )

    def ls(self) -> list[_DirEntry]:
        """List children (convenience wrapper around iterdir)."""
        return list(self.iterdir())

    # -- Delete --------------------------------------------------------------

    def delete(self) -> None:
        """Delete this file."""
        resp = self._get_client().delete(self._url)
        resp.raise_for_status()

    def unlink(self) -> None:
        """Alias for delete(), matching pathlib naming."""
        self.delete()


# ---------------------------------------------------------------------------
# Stream wrappers
# ---------------------------------------------------------------------------


class _BytesReadStream:
    """Streaming binary reader backed by an HTTP GET with iter_bytes."""

    def __init__(self, resource: Resource) -> None:
        self._resource = resource
        self._response: httpx.Response | None = None
        self._stream: Iterator[bytes] | None = None
        self._leftover = bytearray()
        self._exhausted = False

    def __enter__(self) -> _BytesReadStream:
        client = self._resource._get_client()
        self._response = client.send(
            client.build_request("GET", self._resource._url),
            stream=True,
        )
        self._response.raise_for_status()
        self._stream = self._response.iter_bytes(_DEFAULT_CHUNK)
        return self

    def __exit__(self, *exc) -> None:
        if self._response is not None:
            self._response.close()

    def read(self, n: int = -1) -> bytes:
        """Read up to *n* bytes, or all remaining if *n* < 0.

        Returns ``b""`` when the stream is exhausted (EOF).
        """
        if self._stream is None:
            raise RuntimeError("Stream not open — use as context manager")
        if n < 0:
            parts = [bytes(self._leftover)] if self._leftover else []
            self._leftover.clear()
            parts.extend(self._stream)
            self._exhausted = True
            return b"".join(parts)
        # Serve from leftover buffer + stream until we have n bytes or EOF
        buf = self._leftover
        while len(buf) < n and not self._exhausted:
            try:
                buf.extend(next(self._stream))
            except StopIteration:
                self._exhausted = True
        result = bytes(buf[:n])
        self._leftover = buf[n:]
        return result

    def __iter__(self) -> Iterator[bytes]:
        if self._stream is None:
            raise RuntimeError("Stream not open — use as context manager")
        return self._stream


class _TextReadStream:
    """Streaming text reader — decodes bytes stream on the fly."""

    def __init__(self, resource: Resource, encoding: str = "utf-8") -> None:
        self._inner = _BytesReadStream(resource)
        self._encoding = encoding

    def __enter__(self) -> _TextReadStream:
        self._inner.__enter__()
        return self

    def __exit__(self, *exc) -> None:
        self._inner.__exit__(*exc)

    def read(self, n: int = -1) -> str:
        return self._inner.read(n).decode(self._encoding)

    def __iter__(self) -> Iterator[str]:
        for chunk in self._inner:
            yield chunk.decode(self._encoding)


class _BytesWriteStream:
    """Streaming binary writer using chunked transfer encoding.

    Data is streamed to the server incrementally via a background thread.
    The write buffer is flushed when it reaches *chunk_size* or when
    *flush_interval* seconds have elapsed since the last write —
    whichever comes first — so even slow writers don't hold data back
    for too long.
    """

    def __init__(
        self,
        resource: Resource,
        *,
        chunk_size: int = _DEFAULT_CHUNK,
        flush_interval: float = 0.5,
    ) -> None:
        self._resource = resource
        self._chunk_size = chunk_size
        self._flush_interval = flush_interval
        self._queue: queue.Queue[bytes | None] = queue.Queue()
        self._buf = bytearray()
        self._buf_lock = threading.Lock()
        self._closed = False
        self._thread: threading.Thread | None = None
        self._timer: threading.Timer | None = None
        self._error: BaseException | None = None

    def __enter__(self) -> _BytesWriteStream:
        self._thread = threading.Thread(target=self._upload, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        if not self._closed:
            self._closed = True
            with self._buf_lock:
                self._cancel_timer()
                if self._buf:
                    self._queue.put(bytes(self._buf))
                    self._buf.clear()
            self._queue.put(None)  # sentinel — tells generator to stop
        if self._thread is not None:
            self._thread.join()
        if self._error is not None:
            raise self._error

    def write(self, data: bytes) -> int:
        if self._closed:
            raise RuntimeError("Stream is closed")
        if self._error is not None:
            raise self._error
        with self._buf_lock:
            self._buf.extend(data)
            if len(self._buf) >= self._chunk_size:
                self._cancel_timer()
                self._queue.put(bytes(self._buf))
                self._buf.clear()
            else:
                self._reset_timer()
        return len(data)

    # -- internal helpers ----------------------------------------------------

    def _reset_timer(self) -> None:
        self._cancel_timer()
        self._timer = threading.Timer(self._flush_interval, self._timer_flush)
        self._timer.daemon = True
        self._timer.start()

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _timer_flush(self) -> None:
        """Called by the timer thread when flush_interval expires."""
        with self._buf_lock:
            self._timer = None
            if self._buf:
                self._queue.put(bytes(self._buf))
                self._buf.clear()

    def _generate(self) -> Generator[bytes, None, None]:
        while True:
            chunk = self._queue.get()
            if chunk is None:
                break
            yield chunk

    def _upload(self) -> None:
        try:
            client = self._resource._get_client()
            resp = client.put(
                self._resource._url,
                content=self._generate(),
                headers={
                    "Content-Type": "application/octet-stream",
                    "Transfer-Encoding": "chunked",
                },
            )
            resp.raise_for_status()
        except BaseException as e:
            self._error = e


class _TextWriteStream:
    """Streaming text writer — encodes strings and delegates to _BytesWriteStream."""

    def __init__(self, resource: Resource, encoding: str = "utf-8") -> None:
        self._inner = _BytesWriteStream(resource)
        self._encoding = encoding

    def __enter__(self) -> _TextWriteStream:
        self._inner.__enter__()
        return self

    def __exit__(self, *exc) -> None:
        self._inner.__exit__(*exc)

    def write(self, data: str) -> int:
        encoded = data.encode(self._encoding)
        return self._inner.write(encoded)


# ---------------------------------------------------------------------------
# Directory entry
# ---------------------------------------------------------------------------


class _DirEntry:
    """Represents one item returned by iterdir()."""

    def __init__(
        self,
        resource: Resource,
        entry_type: str,
        size: int | None = None,
        mime_type: str | None = None,
    ) -> None:
        self.resource = resource
        self.name = resource.name
        self.type = entry_type
        self.size = size
        self.mime_type = mime_type

    def is_dir(self) -> bool:
        return self.type == "entry"

    def is_file(self) -> bool:
        return self.type == "file"

    def __repr__(self) -> str:
        return f"DirEntry({self.name!r}, type={self.type!r})"

    def __truediv__(self, other: str) -> Resource:
        return self.resource / other
