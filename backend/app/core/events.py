"""Server-Sent Events hub for real-time I/O activity notifications."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field

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


class EventHub:
    """Simple pub/sub for I/O events, keyed by user_id."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[IoEvent]]] = {}

    def subscribe(self, user_id: str) -> asyncio.Queue[IoEvent]:
        queue: asyncio.Queue[IoEvent] = asyncio.Queue(maxsize=256)
        self._subscribers.setdefault(user_id, []).append(queue)
        return queue

    def unsubscribe(self, user_id: str, queue: asyncio.Queue[IoEvent]) -> None:
        queues = self._subscribers.get(user_id, [])
        if queue in queues:
            queues.remove(queue)

    def publish(self, user_id: str, event: IoEvent) -> None:
        """Publish an event to all subscribers for a given user."""
        for queue in self._subscribers.get(user_id, []):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass  # Drop if subscriber is too slow


# Global singleton
event_hub = EventHub()
