import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import decode_access_token
from app.models import Attachment, Entry, Notebook, Permission, User
from app.schemas import AttachmentOut

router = APIRouter(prefix="/attachments", tags=["attachments"])

_bearer = HTTPBearer(auto_error=False)


class OptionalBearer:
    """Dependency that returns a User if a Bearer token is present, else None."""
    async def __call__(
        self,
        request: Request,
        creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
        db: Session = Depends(get_db),
    ) -> User | None:
        if creds is None:
            return None
        try:
            payload = decode_access_token(creds.credentials)
            return db.query(User).filter(User.id == payload["sub"]).first()
        except Exception:
            return None

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


def _can_access_entry(db: Session, user: User, entry_id: str, level: str = "read") -> Entry:
    entry = db.query(Entry).filter(Entry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    notebook = db.query(Notebook).filter(Notebook.id == entry.notebook_id).first()
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")

    if notebook.owner_id == user.id or user.role == "admin":
        return entry

    levels = {"read": 0, "write": 1, "admin": 2}

    for res_type, res_id in [("entry", entry.id), ("notebook", notebook.id)]:
        perm = (
            db.query(Permission)
            .filter(
                Permission.subject_id == user.id,
                Permission.resource_type == res_type,
                Permission.resource_id == res_id,
            )
            .first()
        )
        if perm and levels.get(perm.access_level, -1) >= levels[level]:
            return entry

    raise HTTPException(status_code=403, detail="Insufficient permissions")


@router.post("/", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    entry_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upload a file attachment to an entry."""
    _can_access_entry(db, user, entry_id, level="write")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit",
        )

    filename = file.filename or "unnamed"
    file_id = uuid.uuid4().hex[:12]
    dest_dir = settings.storage_dir / entry_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    storage_path = dest_dir / f"{file_id}_{filename}"
    storage_path.write_bytes(content)

    # Classify attachment type
    mime = file.content_type or "application/octet-stream"
    if mime.startswith("image/"):
        att_type = "image"
    elif filename.lower().endswith((".xlsx", ".xls", ".csv")):
        att_type = "excel"
    else:
        att_type = "file"

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
    token: str | None = None,
    user: User | None = Depends(OptionalBearer()),
):
    """Download an attachment file. Auth via Bearer header or ?token= query param."""
    # Resolve user from Bearer header or query-param token
    resolved_user = user
    if resolved_user is None and token:
        try:
            payload = decode_access_token(token)
            resolved_user = db.query(User).filter(User.id == payload["sub"]).first()
        except Exception:
            pass
    if resolved_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    _can_access_entry(db, user=resolved_user, entry_id=attachment.entry_id, level="read")

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
    _can_access_entry(db, user, entry_id, level="read")
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

    _can_access_entry(db, user, attachment.entry_id, level="write")

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
    _can_access_entry(db, user, attachment.entry_id, level="write")
    _can_access_entry(db, user, body.entry_id, level="write")

    attachment.entry_id = body.entry_id
    db.commit()
    db.refresh(attachment)
    return attachment
