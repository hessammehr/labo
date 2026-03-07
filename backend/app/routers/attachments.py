import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.access import require_access
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import Attachment, Entry, User
from app.schemas import AttachmentOut

router = APIRouter(prefix="/attachments", tags=["attachments"])


@router.post("/", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED)
def upload_attachment(
    entry_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upload an attachment to an entry."""
    entry = db.query(Entry).filter(Entry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    require_access(db, user, "entry", entry_id, "write")

    content = file.file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 50 MB)")

    mime = file.content_type or "application/octet-stream"
    filename = file.filename or "unnamed"

    # Classify type
    if mime.startswith("image/"):
        att_type = "image"
    elif filename.lower().endswith((".xlsx", ".xls", ".csv")):
        att_type = "excel"
    else:
        att_type = "file"

    # Store file on disk
    entry_dir = settings.storage_dir / entry_id
    entry_dir.mkdir(parents=True, exist_ok=True)
    prefix = uuid.uuid4().hex[:12]
    storage_path = entry_dir / f"{prefix}_{filename}"
    storage_path.write_bytes(content)

    attachment = Attachment(
        entry_id=entry_id,
        type=att_type,
        filename=filename,
        mime_type=mime,
        size=len(content),
        storage_uri=str(storage_path),
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return attachment


@router.get("/{attachment_id}")
def download_attachment(
    attachment_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Download an attachment file."""
    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    require_access(db, user, "entry", attachment.entry_id, "read")

    from pathlib import Path

    path = Path(attachment.storage_uri)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path=path,
        media_type=attachment.mime_type,
        filename=attachment.filename,
    )


@router.get("/entry/{entry_id}", response_model=list[AttachmentOut])
def list_attachments(
    entry_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all attachments for an entry."""
    require_access(db, user, "entry", entry_id, "read")
    return db.query(Attachment).filter(Attachment.entry_id == entry_id).all()


@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attachment(
    attachment_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete an attachment."""
    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    require_access(db, user, "entry", attachment.entry_id, "write")

    from pathlib import Path

    path = Path(attachment.storage_uri)
    if path.exists():
        path.unlink()

    db.delete(attachment)
    db.commit()


class AttachmentMove(BaseModel):
    entry_id: str


@router.patch("/{attachment_id}", response_model=AttachmentOut)
def move_attachment(
    attachment_id: str,
    body: AttachmentMove,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Move an attachment to a different entry."""
    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    # Require write access on both source and destination entries
    require_access(db, user, "entry", attachment.entry_id, "write")
    require_access(db, user, "entry", body.entry_id, "write")

    attachment.entry_id = body.entry_id
    db.commit()
    db.refresh(attachment)
    return attachment
