"""SSE endpoint for real-time I/O activity notifications."""

import asyncio

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.events import event_hub
from app.models import User

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/io")
async def io_events(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """SSE stream of file I/O events for the current user's resources."""
    queue = event_hub.subscribe(user.id)

    async def stream():
        try:
            # Send initial keepalive
            yield ": connected\n\n"
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield event.to_sse()
                except asyncio.TimeoutError:
                    # Send keepalive comment
                    yield ": keepalive\n\n"
        finally:
            event_hub.unsubscribe(user.id, queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
