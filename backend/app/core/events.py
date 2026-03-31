"""Server-Sent Events hubs for real-time notifications."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Generic, Protocol, TypeVar


class SseEvent(Protocol):
    def to_sse(self) -> str:
        ...


@dataclass
class IoEvent:
    """A single file I/O event."""
    resource_type: str  # "notebook" | "entry"
    resource_id: str
    entry_id: str
    filename: str
    direction: str  # "read" | "write"
    timestamp: float = field(default_factory=time.time)

    def to_sse(self) -> str:
        data = json.dumps({
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "entry_id": self.entry_id,
            "filename": self.filename,
            "direction": self.direction,
            "timestamp": self.timestamp,
        })
        return f"data: {data}\n\n"


@dataclass
class EntryVersionEvent:
    """An entry version bump notification for collaborative editing."""
    notebook_id: str
    entry_id: str
    version: int
    updated_at: datetime
    timestamp: float = field(default_factory=time.time)

    def to_sse(self) -> str:
        data = json.dumps(
            {
                "notebook_id": self.notebook_id,
                "entry_id": self.entry_id,
                "version": self.version,
                "updated_at": self.updated_at.isoformat(),
                "timestamp": self.timestamp,
            }
        )
        return f"data: {data}\n\n"


TEvent = TypeVar("TEvent", bound=SseEvent)


class EventHub(Generic[TEvent]):
    """Simple pub/sub keyed by user_id."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[TEvent]]] = {}

    def subscribe(self, user_id: str) -> asyncio.Queue[TEvent]:
        queue: asyncio.Queue[TEvent] = asyncio.Queue(maxsize=256)
        self._subscribers.setdefault(user_id, []).append(queue)
        return queue

    def unsubscribe(self, user_id: str, queue: asyncio.Queue[TEvent]) -> None:
        queues = self._subscribers.get(user_id, [])
        if queue in queues:
            queues.remove(queue)

    def publish(self, user_id: str, event: TEvent) -> None:
        """Publish an event to all subscribers for a given user."""
        for queue in self._subscribers.get(user_id, []):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass  # Drop if subscriber is too slow


# Global singletons
io_event_hub = EventHub[IoEvent]()
entry_event_hub = EventHub[EntryVersionEvent]()
