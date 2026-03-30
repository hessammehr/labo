"""Token-scoped file I/O API for programmatic access.

Paths are resolved relative to the token's scoped resource:
  - Notebook-scoped: {entry_title}/{filename}
  - Entry-scoped:    {filename}

Supports streaming reads and chunked streaming writes.
"""

import json
import mimetypes
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.events import IoEvent, event_hub
from app.core.security import hash_api_key
from app.models import Attachment, Entry, Notebook, ScopedToken
from app.services.markdown import blocks_to_markdown

router = APIRouter(prefix="/v1/files", tags=["files"])

STREAM_CHUNK_SIZE = 64 * 1024  # 64 KB


def _resolve_token(db: Session, authorization: str | None) -> ScopedToken:
    """Extract and validate a Bearer token from the Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    raw_token = authorization[7:]
    token_hash = hash_api_key(raw_token)
    token = db.query(ScopedToken).filter(ScopedToken.token_hash == token_hash).first()
    if not token:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Update last_used_at
    token.last_used_at = datetime.now(timezone.utc)
    db.commit()

    return token


def _resolve_path(
    db: Session,
    token: ScopedToken,
    path: str,
) -> tuple[Entry, Attachment | None]:
    """Resolve a path string to an Entry and optionally an Attachment.

    Returns (entry, attachment) where attachment is None for directory-level access.
    """
    parts = path.strip("/").split("/") if path.strip("/") else []

    if token.resource_type == "notebook":
        notebook = db.query(Notebook).filter(Notebook.id == token.resource_id).first()
        if not notebook:
            raise HTTPException(status_code=404, detail="Notebook not found")

        if len(parts) == 0:
            # Listing notebook entries — return (None, None) to signal directory listing
            return None, None

        entry_title = parts[0]
        entry = (
            db.query(Entry)
            .filter(Entry.notebook_id == notebook.id, Entry.title == entry_title)
            .first()
        )
        if not entry:
            raise HTTPException(status_code=404, detail=f"Entry '{entry_title}' not found")

        if len(parts) == 1:
            return entry, None

        filename = "/".join(parts[1:])
        attachment = (
            db.query(Attachment)
            .filter(Attachment.entry_id == entry.id, Attachment.filename == filename)
            .first()
        )
        return entry, attachment

    elif token.resource_type == "entry":
        entry = db.query(Entry).filter(Entry.id == token.resource_id).first()
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found")

        if len(parts) == 0:
            return entry, None

        filename = "/".join(parts)
        attachment = (
            db.query(Attachment)
            .filter(Attachment.entry_id == entry.id, Attachment.filename == filename)
            .first()
        )
        return entry, attachment

    else:
        raise HTTPException(status_code=400, detail="Unsupported resource type")


@router.get("/{path:path}")
def read_file(
    path: str,
    request: Request,
    content: str | None = Query(None, description="Entry content format: 'markdown' or 'blocks'"),
    db: Session = Depends(get_db),
):
    """Read a file or list directory contents.

    Pass ``?content=markdown`` or ``?content=blocks`` to read the entry's
    text content instead of listing attachments.
    """
    token = _resolve_token(db, request.headers.get("authorization"))
    entry, attachment = _resolve_path(db, token, path)

    # Entry content access  (?content=markdown|blocks)
    if content is not None:
        if content not in ("markdown", "blocks"):
            raise HTTPException(status_code=400, detail="content must be 'markdown' or 'blocks'")
        if entry is None:
            raise HTTPException(status_code=400, detail="Path must point to an entry to read content")
        if attachment is not None:
            raise HTTPException(status_code=400, detail="Path must point to an entry, not a file")
        if content == "markdown":
            md = blocks_to_markdown(entry.content_blocks or [], title=entry.title)
            return PlainTextResponse(md, media_type="text/markdown")
        else:
            return JSONResponse({"title": entry.title, "blocks": entry.content_blocks or []})

    # Directory listing
    if attachment is None:
        if entry is None:
            # Notebook root — list entries
            notebook = db.query(Notebook).filter(Notebook.id == token.resource_id).first()
            entries = db.query(Entry).filter(Entry.notebook_id == notebook.id).all()
            return [{"name": e.title, "type": "entry"} for e in entries]
        else:
            # List attachments in entry
            attachments = db.query(Attachment).filter(Attachment.entry_id == entry.id).all()
            return [
                {"name": a.filename, "type": "file", "size": a.size, "mime_type": a.mime_type}
                for a in attachments
            ]

    # File read — stream it
    file_path = Path(attachment.storage_uri)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    def iterfile():
        last_event_at = 0.0
        event_interval = 0.5  # seconds — throttle to avoid flooding SSE
        with open(file_path, "rb") as f:
            while chunk := f.read(STREAM_CHUNK_SIZE):
                now = time.monotonic()
                if now - last_event_at >= event_interval:
                    last_event_at = now
                    event_hub.publish(
                        token.created_by,
                        IoEvent(
                            resource_type=token.resource_type,
                            resource_id=token.resource_id,
                            entry_id=entry.id,
                            filename=attachment.filename,
                            direction="read",
                        ),
                    )
                yield chunk

    return StreamingResponse(
        iterfile(),
        media_type=attachment.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{attachment.filename}"',
            "Content-Length": str(attachment.size),
        },
    )


@router.put("/{path:path}", status_code=status.HTTP_201_CREATED)
async def write_file(
    path: str,
    request: Request,
    content: str | None = Query(None, description="Entry content format: 'markdown' or 'blocks'"),
    db: Session = Depends(get_db),
):
    """Write (create or overwrite) a file via streaming upload.

    Send the file body directly as the request body (not multipart).
    Set Content-Type to the file's MIME type.

    Pass ``?content=markdown`` or ``?content=blocks`` to write the entry's
    text content instead of an attachment.
    """
    token = _resolve_token(db, request.headers.get("authorization"))

    if token.access_level != "readwrite":
        raise HTTPException(status_code=403, detail="Token does not have write access")

    # Entry content write  (?content=blocks)
    if content is not None:
        if content != "blocks":
            raise HTTPException(status_code=400, detail="Only ?content=blocks is supported for writes")

        entry, attachment = _resolve_path(db, token, path)
        if entry is None:
            raise HTTPException(status_code=400, detail="Path must point to an entry to write content")
        if attachment is not None:
            raise HTTPException(status_code=400, detail="Path must point to an entry, not a file")

        payload = json.loads(await request.body())
        if not isinstance(payload, dict) or "blocks" not in payload:
            raise HTTPException(status_code=400, detail='Expected {"blocks": [...], "title": "..."}')

        entry.content_blocks = payload["blocks"]
        db.commit()
        db.refresh(entry)
        return {"status": "updated"}

    # Parse the path to find entry + filename
    parts = path.strip("/").split("/") if path.strip("/") else []
    if not parts:
        raise HTTPException(status_code=400, detail="Path must include a filename")

    if token.resource_type == "notebook":
        if len(parts) < 2:
            raise HTTPException(
                status_code=400,
                detail="Notebook-scoped path must be entry_title/filename",
            )
        entry_title = parts[0]
        filename = "/".join(parts[1:])

        notebook = db.query(Notebook).filter(Notebook.id == token.resource_id).first()
        if not notebook:
            raise HTTPException(status_code=404, detail="Notebook not found")

        entry = (
            db.query(Entry)
            .filter(Entry.notebook_id == notebook.id, Entry.title == entry_title)
            .first()
        )
        if not entry:
            raise HTTPException(status_code=404, detail=f"Entry '{entry_title}' not found")

    elif token.resource_type == "entry":
        filename = "/".join(parts)
        entry = db.query(Entry).filter(Entry.id == token.resource_id).first()
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found")
    else:
        raise HTTPException(status_code=400, detail="Unsupported resource type")

    # Stream request body to disk, emitting periodic SSE events so the
    # UI shows upload activity throughout (not just at the end).
    entry_dir = settings.storage_dir / entry.id
    entry_dir.mkdir(parents=True, exist_ok=True)
    storage_path = entry_dir / filename

    total_size = 0
    max_size = 50 * 1024 * 1024  # 50 MB
    last_event_at = 0.0
    event_interval = 0.5  # seconds — throttle to avoid flooding SSE

    with open(storage_path, "wb") as f:
        async for chunk in request.stream():
            total_size += len(chunk)
            if total_size > max_size:
                f.close()
                storage_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="File too large (max 50 MB)")
            f.write(chunk)

            now = time.monotonic()
            if now - last_event_at >= event_interval:
                last_event_at = now
                event_hub.publish(
                    token.created_by,
                    IoEvent(
                        resource_type=token.resource_type,
                        resource_id=token.resource_id,
                        entry_id=entry.id,
                        filename=filename,
                        direction="write",
                    ),
                )

    # Determine MIME type
    content_type = request.headers.get("content-type", "")
    if not content_type or content_type == "application/octet-stream":
        guessed, _ = mimetypes.guess_type(filename)
        content_type = guessed or "application/octet-stream"

    # Classify attachment type
    if content_type.startswith("image/"):
        att_type = "image"
    elif filename.lower().endswith((".xlsx", ".xls", ".csv")):
        att_type = "excel"
    else:
        att_type = "file"

    # Upsert attachment record
    existing = (
        db.query(Attachment)
        .filter(Attachment.entry_id == entry.id, Attachment.filename == filename)
        .first()
    )

    if existing:
        existing.size = total_size
        existing.mime_type = content_type
        existing.type = att_type
        existing.storage_uri = str(storage_path)
        db.commit()
        db.refresh(existing)
        result = {
            "id": existing.id,
            "filename": existing.filename,
            "size": existing.size,
            "mime_type": existing.mime_type,
            "status": "updated",
        }
    else:
        attachment = Attachment(
            entry_id=entry.id,
            type=att_type,
            filename=filename,
            mime_type=content_type,
            size=total_size,
            storage_uri=str(storage_path),
        )
        db.add(attachment)
        db.commit()
        db.refresh(attachment)
        result = {
            "id": attachment.id,
            "filename": attachment.filename,
            "size": attachment.size,
            "mime_type": attachment.mime_type,
            "status": "created",
        }

    # Emit write event
    event_hub.publish(
        token.created_by,
        IoEvent(
            resource_type=token.resource_type,
            resource_id=token.resource_id,
            entry_id=entry.id,
            filename=filename,
            direction="write",
        ),
    )

    return result


@router.patch("/{path:path}")
async def rename_resource(
    path: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Rename an entry or attachment.

    Send a JSON body with ``{"name": "new name"}``.
    Returns the new path.
    """
    token = _resolve_token(db, request.headers.get("authorization"))

    if token.access_level != "readwrite":
        raise HTTPException(status_code=403, detail="Token does not have write access")

    entry, attachment = _resolve_path(db, token, path)

    if entry is None:
        raise HTTPException(status_code=400, detail="Path must point to an entry or file")

    body = json.loads(await request.body())
    new_name = body.get("name") if isinstance(body, dict) else None
    if not new_name or not isinstance(new_name, str):
        raise HTTPException(status_code=400, detail='Expected JSON body: {"name": "new name"}')
    if "/" in new_name:
        raise HTTPException(status_code=400, detail="Name must not contain '/'; use rename, not move")

    if attachment is not None:
        # Rename attachment
        old_path = Path(attachment.storage_uri)
        new_storage_path = old_path.parent / new_name
        if old_path.exists():
            old_path.rename(new_storage_path)
        attachment.filename = new_name
        attachment.storage_uri = str(new_storage_path)
        db.commit()

        # Build new API path
        if token.resource_type == "notebook":
            new_full_path = f"{entry.title}/{new_name}"
        else:
            new_full_path = new_name
        return {"path": new_full_path, "status": "renamed"}
    else:
        # Rename entry
        entry.title = new_name
        db.commit()

        if token.resource_type == "notebook":
            new_full_path = new_name
        else:
            new_full_path = ""
        return {"path": new_full_path, "status": "renamed"}


@router.delete("/{path:path}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(
    path: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Delete a file."""
    token = _resolve_token(db, request.headers.get("authorization"))

    if token.access_level != "readwrite":
        raise HTTPException(status_code=403, detail="Token does not have write access")

    entry, attachment = _resolve_path(db, token, path)

    if attachment is None:
        raise HTTPException(status_code=400, detail="Path must point to a file, not a directory")

    file_path = Path(attachment.storage_uri)
    if file_path.exists():
        file_path.unlink()

    db.delete(attachment)
    db.commit()
