"""Marimo-compatible reactive Resource.

Usage in a marimo notebook::

    from labo.marimo import Resource

    # Same API as labo.Resource, but with reactive extras
    r = Resource("https://labo.local", token)
    entry = r / "Experiment 1"

    # Reactive listing — cells re-run when files change on the server
    files = entry.children

    # Interactive file browser widget
    browser = entry.pick()
    browser  # display in cell

    # In another cell — value is a Resource (or None)
    selected = browser.value
    if selected:
        data = selected.read_bytes()
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Callable, Literal, Sequence

import httpx

try:
    import marimo as mo
    from marimo._plugins.ui._core.ui_element import Function, UIElement
    from marimo._plugins.ui._impl.file_browser import (
        ListDirectoryArgs,
        ListDirectoryResponse,
        TypedFileBrowserFileInfo,
        file_browser,
        natural_sort,
    )
except ImportError as e:
    raise ImportError(
        "labo.marimo requires marimo. Install it with: pip install labo[marimo]"
    ) from e

from labo._resource import Resource as _BaseResource, _DirEntry

logger = logging.getLogger(__name__)

_SSE_RECONNECT_BASE = 1.0
_SSE_RECONNECT_MAX = 30.0


# ---------------------------------------------------------------------------
# File browser adapted for Labo Resources
# ---------------------------------------------------------------------------


class LaboFileBrowser(file_browser):
    """A ``mo.ui.file_browser`` adapted to browse remote Labo resources.

    Instead of navigating the local filesystem, this widget lists entries
    and files from a Labo server via the Resource API.

    When ``multiple=False`` (the default for :meth:`Resource.pick`),
    ``browser.value`` is a single :class:`Resource` or ``None``.
    When ``multiple=True``, it's a ``list[Resource]``.

    This reuses marimo's built-in file browser frontend component
    (``marimo-file-browser``) — only the backend listing/selection logic
    is replaced.
    """

    def __init__(
        self,
        resource: Resource,
        *,
        filetypes: Sequence[str] | None = None,
        selection_mode: Literal["file", "directory"] = "file",
        multiple: bool = True,
        restrict_navigation: bool = False,
        limit: int = 10_000,
        label: str = "",
        on_change: Callable | None = None,
    ) -> None:
        self._root_resource = resource
        self._selection_mode = selection_mode
        self._multiple = multiple

        # Normalize filetypes for case-insensitive matching
        if filetypes:
            self._filetypes = {
                ft.lower() if ft.startswith(".") else f".{ft.lower()}"
                for ft in filetypes
            }
        else:
            self._filetypes = set()

        self._restrict_navigation = restrict_navigation
        self._limit = limit

        # The "initial path" the frontend sees is the resource's logical path.
        # We use "/" as root so the frontend has an absolute-looking path.
        initial_path = "/" + resource._path if resource._path else "/"

        # Bypass file_browser.__init__ (which validates local paths) and
        # call UIElement.__init__ directly with the same frontend component.
        UIElement.__init__(
            self,
            component_name="marimo-file-browser",
            initial_value=[],
            label=label,
            on_change=on_change,
            args={
                "initial-path": initial_path,
                "selection-mode": selection_mode,
                "filetypes": list(self._filetypes) if self._filetypes else [],
                "multiple": multiple,
                "restrict-navigation": restrict_navigation,
            },
            functions=(
                Function(
                    name="list_directory",
                    arg_cls=ListDirectoryArgs,
                    function=self._list_directory,
                ),
            ),
        )

    def _path_to_resource(self, path_str: str) -> Resource:
        """Convert a frontend path string back to a Resource."""
        # Strip the leading "/" we added for the frontend
        rel = path_str.lstrip("/")
        return Resource(
            self._root_resource._base_url,
            self._root_resource._token,
            _path=rel,
            _client=self._root_resource._client,
        )

    def _list_directory(self, args: ListDirectoryArgs) -> ListDirectoryResponse:
        """List the contents of a Labo resource directory."""
        resource = self._path_to_resource(args.path)

        # Restrict navigation: don't allow navigating above root
        if self._restrict_navigation:
            root = "/" + self._root_resource._path if self._root_resource._path else "/"
            requested = args.path.rstrip("/")
            if not requested.startswith(root.rstrip("/")):
                raise RuntimeError(
                    "Navigation is restricted; cannot navigate above the initial path."
                )

        entries = resource.ls()
        # Sort naturally by name
        entries.sort(key=lambda e: natural_sort(e.name))

        folders: list[TypedFileBrowserFileInfo] = []
        files: list[TypedFileBrowserFileInfo] = []

        for entry in entries:
            is_directory = entry.is_dir()

            # Apply selection_mode filter
            if self._selection_mode == "directory" and not is_directory:
                continue

            # Apply filetype filter
            if self._filetypes and not is_directory:
                suffix = ("." + entry.name.rsplit(".", 1)[1]).lower() if "." in entry.name else ""
                if suffix not in self._filetypes:
                    continue

            # Build the full path as the frontend sees it
            child_path = f"/{entry.resource._path}" if entry.resource._path else "/"

            info = TypedFileBrowserFileInfo(
                id=child_path,
                path=child_path,
                name=entry.name,
                is_directory=is_directory,
            )

            if is_directory:
                folders.append(info)
            else:
                files.append(info)

            if len(folders) + len(files) >= self._limit:
                break

        all_files = folders + files
        return ListDirectoryResponse(
            files=all_files,
            total_count=len(entries),
            is_truncated=len(all_files) < len(entries),
        )

    def _convert_value(
        self, value: list[TypedFileBrowserFileInfo]
    ) -> Resource | list[Resource] | None:
        """Convert frontend selection to Resource(s).

        When ``multiple=False``, returns a single :class:`Resource` or
        ``None``.  When ``multiple=True``, returns a list of Resources.
        """
        resources = [self._path_to_resource(item["path"]) for item in value]
        if self._multiple:
            return resources
        return resources[0] if resources else None


# ---------------------------------------------------------------------------
# Reactive Resource
# ---------------------------------------------------------------------------


class Resource(_BaseResource):
    """A marimo-reactive drop-in replacement for :class:`labo.Resource`.

    Inherits the full pathlib-style API (``/``, ``read_bytes``, ``open``, etc.)
    and adds:

    * :attr:`children` — a reactive property backed by ``mo.state`` that
      triggers cell re-execution when files are added, removed, or modified.
    * :meth:`pick` — returns a :class:`LaboFileBrowser` widget (adapted
      ``mo.ui.file_browser``) for interactive file/entry selection.

    SSE listening is started lazily on first access to :attr:`children` or
    :meth:`pick`, and is shared across all ``Resource`` instances that share
    the same underlying HTTP client (i.e. same base_url + token).
    """

    # Class-level registry: client id → _SSEListener
    _listeners: dict[int, _SSEListener] = {}
    _listeners_lock = threading.Lock()

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        _path: str = "",
        _client: httpx.Client | None = None,
    ) -> None:
        super().__init__(base_url, token, _path=_path, _client=_client)
        self._state: tuple[Any, Any] | None = None  # (getter, setter)

    # -- Override / to return marimo Resource --------------------------------

    def __truediv__(self, other: str) -> Resource:
        new_path = f"{self._path}/{other}".strip("/") if self._path else other.strip("/")
        return Resource(
            self._base_url,
            self._token,
            _path=new_path,
            _client=self._client,
        )

    @property
    def parent(self) -> Resource:
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

    # -- Reactive state ------------------------------------------------------

    def _ensure_state(self) -> tuple[Any, Any]:
        """Lazily create mo.state and start SSE listener."""
        if self._state is None:
            self._state = mo.state(self.ls())
            self._ensure_sse_listener()
        return self._state

    def _ensure_sse_listener(self) -> None:
        """Start a shared SSE listener for this client (one per base_url+token)."""
        client = self._get_client()
        client_id = id(client)
        with Resource._listeners_lock:
            if client_id not in Resource._listeners:
                listener = _SSEListener(client, self._base_url, self._token)
                Resource._listeners[client_id] = listener
                listener.start()
            Resource._listeners[client_id].register(self)

    @property
    def children(self) -> list[_DirEntry]:
        """Reactive listing of child resources.

        Reading this property in a marimo cell makes that cell re-run
        whenever the server reports file changes (via SSE) for this path.
        """
        getter, _ = self._ensure_state()
        return getter()

    def _on_change(self) -> None:
        """Called by the SSE listener when a relevant event arrives."""
        if self._state is not None:
            _, setter = self._state
            try:
                setter(self.ls())
            except Exception:
                logger.exception("Failed to refresh listing for %s", self._path)

    # -- File browser widget -------------------------------------------------

    def pick(
        self,
        *,
        filetypes: Sequence[str] | None = None,
        selection_mode: Literal["file", "directory"] = "file",
        multiple: bool = False,
        restrict_navigation: bool = True,
        label: str = "",
        on_change: Callable | None = None,
    ) -> LaboFileBrowser:
        """Return a file browser widget for picking files from this resource.

        Uses marimo's built-in ``file_browser`` frontend with a Labo backend.

        Usage::

            browser = entry.pick()
            browser  # display in cell

            # In another cell:
            selected = browser.value  # Resource or None
            if selected:
                data = selected.read_bytes()

        Args:
            filetypes: File extensions to show (e.g. ``[".csv", ".xlsx"]``).
            selection_mode: ``"file"`` or ``"directory"``.
            multiple: Allow selecting multiple items.
            restrict_navigation: Prevent navigating above this resource.
            label: Markdown label for the widget.
            on_change: Callback when selection changes.
        """
        return LaboFileBrowser(
            self,
            filetypes=filetypes,
            selection_mode=selection_mode,
            multiple=multiple,
            restrict_navigation=restrict_navigation,
            label=label or f"Browse {self._path or '/'}",
            on_change=on_change,
        )

    # -- Cleanup -------------------------------------------------------------

    def close(self) -> None:
        if self._client is not None:
            client_id = id(self._client)
            with Resource._listeners_lock:
                listener = Resource._listeners.pop(client_id, None)
            if listener is not None:
                listener.stop()
        super().close()


# ---------------------------------------------------------------------------
# SSE listener
# ---------------------------------------------------------------------------


class _SSEListener:
    """Background thread that consumes the /api/events/io SSE stream
    and notifies registered Resource instances of relevant changes."""

    def __init__(self, client: httpx.Client, base_url: str, token: str) -> None:
        self._client = client
        self._base_url = base_url
        self._token = token
        self._resources: dict[str, Resource] = {}  # path → Resource
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def register(self, resource: Resource) -> None:
        with self._lock:
            self._resources[resource._path] = resource

    def unregister(self, resource: Resource) -> None:
        with self._lock:
            self._resources.pop(resource._path, None)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="labo-sse")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:
        """Connect to SSE with exponential backoff reconnection."""
        delay = _SSE_RECONNECT_BASE
        while not self._stop_event.is_set():
            try:
                self._stream()
                delay = _SSE_RECONNECT_BASE  # reset on clean disconnect
            except Exception:
                logger.debug("SSE connection lost, reconnecting in %.1fs", delay)
                self._stop_event.wait(delay)
                delay = min(delay * 2, _SSE_RECONNECT_MAX)

    def _stream(self) -> None:
        """Open an SSE connection and dispatch events."""
        sse_url = f"{self._base_url}/api/events/io"
        with httpx.Client(
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=httpx.Timeout(None),
        ) as sse_client:
            with sse_client.stream("GET", sse_url) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if self._stop_event.is_set():
                        return
                    if not line.startswith("data: "):
                        continue
                    self._dispatch(line[6:])

    def _dispatch(self, raw: str) -> None:
        """Parse an SSE data payload and notify matching resources."""
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            return

        entry_id = event.get("entry_id", "")
        filename = event.get("filename", "")

        with self._lock:
            for path, resource in self._resources.items():
                if self._is_relevant(path, entry_id, filename):
                    resource._on_change()

    @staticmethod
    def _is_relevant(watched_path: str, entry_id: str, filename: str) -> bool:
        """Check if an event for entry_id/filename is relevant to watched_path."""
        if not watched_path:
            return True
        if watched_path == entry_id or watched_path.endswith(f"/{entry_id}"):
            return True
        if entry_id.startswith(watched_path + "/"):
            return True
        return False
