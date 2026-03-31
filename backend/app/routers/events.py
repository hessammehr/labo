"""SSE endpoint for real-time I/O activity notifications."""

import asyncio

from fastapi import APIRouter, Cookie, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.events import entry_event_hub, io_event_hub
from app.core.security import hash_api_key
from app.models import ApiKey, Session, User

router = APIRouter(prefix="/events", tags=["events"])


def _authenticate_eagerly(
    session_cookie: str | None,
    x_api_key: str | None,
) -> str:
    """Authenticate using a short-lived DB session and return the user ID.

    This avoids holding a DB connection open for the entire SSE stream.
    """
    from datetime import datetime, timezone

    db = SessionLocal()
    try:
        user: User | None = None

        if session_cookie:
            session = db.query(Session).filter(Session.id == session_cookie).first()
            if session:
                now = datetime.now(timezone.utc)
                expires = session.expires_at
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                if expires > now:
                    user = session.user

        if user is None and x_api_key:
            key_hash = hash_api_key(x_api_key)
            api_key = db.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()
            if api_key:
                user = api_key.user

        if user is None or user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )

        return user.id
    finally:
        db.close()


@router.get("/io")
async def io_events(
    request: Request,
    session_cookie: str | None = Cookie(None, alias=settings.session_cookie_name),
    x_api_key: str | None = Header(None),
):
    """SSE stream of file I/O events for the current user's resources."""
    # Authenticate eagerly and release the DB connection before streaming.
    user_id = _authenticate_eagerly(session_cookie, x_api_key)

    queue = io_event_hub.subscribe(user_id)

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
            io_event_hub.unsubscribe(user_id, queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/entries")
async def entry_events(
    request: Request,
    session_cookie: str | None = Cookie(None, alias=settings.session_cookie_name),
    x_api_key: str | None = Header(None),
):
    """SSE stream of entry version update events for the current user."""
    user_id = _authenticate_eagerly(session_cookie, x_api_key)

    queue = entry_event_hub.subscribe(user_id)

    async def stream():
        try:
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield event.to_sse()
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            entry_event_hub.unsubscribe(user_id, queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
