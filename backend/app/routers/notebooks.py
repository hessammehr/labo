from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pathlib import Path
import sqlalchemy as sa
from sqlalchemy.orm import Session

from pydantic import BaseModel
from app.core.access import require_access, user_sharing_status
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.events import EntryVersionEvent, entry_event_hub
from app.models import Attachment, Entry, Notebook, Permission, User
from app.schemas import NotebookCreate, NotebookOut, NotebookUpdate, LaboImportResult
from app.services.export import (
    EXPORT_FORMATS,
    AttachmentInfo,
    collect_attachment_ids,
    export_document,
    export_labo_archive_notebook,
    notebook_to_markdown,
    read_labo_archive,
    _rewrite_attachment_urls,
)

router = APIRouter(prefix="/notebooks", tags=["notebooks"])


@router.get("/", response_model=list[NotebookOut])
def list_notebooks(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role == "admin":
        notebooks = db.query(Notebook).order_by(Notebook.position, Notebook.created_at).all()
    else:
        notebooks = (
            db.query(Notebook)
            .filter(
                Notebook.id.in_(
                    db.query(Permission.resource_id).filter(
                        Permission.subject_id == user.id,
                        Permission.resource_type == "notebook",
                    )
                )
            )
            .order_by(Notebook.position, Notebook.created_at)
            .all()
        )

    # Annotate each notebook with sharing info
    result = []
    for nb in notebooks:
        out = NotebookOut.model_validate(nb)
        out.sharing_level = user_sharing_status(db, user.id, nb.author_id, "notebook", nb.id)
        result.append(out)
    return result


@router.post("/", response_model=NotebookOut, status_code=status.HTTP_201_CREATED)
def create_notebook(
    body: NotebookCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Place new notebook at the end of the user's list
    max_pos = (
        db.query(sa.func.max(Notebook.position))
        .join(Permission, sa.and_(
            Permission.resource_id == Notebook.id,
            Permission.resource_type == "notebook",
            Permission.subject_id == user.id,
        ))
        .scalar()
    )
    next_pos = (max_pos or 0) + 1
    notebook = Notebook(author_id=user.id, title=body.title, description=body.description, position=next_pos)
    db.add(notebook)
    db.flush()  # get notebook.id

    # Creator becomes owner via Permission row
    perm = Permission(
        subject_id=user.id,
        resource_type="notebook",
        resource_id=notebook.id,
        access_level="owner",
    )
    db.add(perm)
    db.commit()
    db.refresh(notebook)
    return notebook


class ReorderRequest(BaseModel):
    ordered_ids: list[str]


@router.patch("/reorder", status_code=status.HTTP_204_NO_CONTENT)
def reorder_notebooks(
    body: ReorderRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Set the display order of notebooks for the current user."""
    for idx, notebook_id in enumerate(body.ordered_ids):
        nb = db.query(Notebook).filter(Notebook.id == notebook_id).first()
        if nb:
            nb.position = idx
    db.commit()


@router.get("/{notebook_id}", response_model=NotebookOut)
def get_notebook(
    notebook_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    notebook = db.query(Notebook).filter(Notebook.id == notebook_id).first()
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")
    require_access(db, user, "notebook", notebook_id, "read")
    return notebook


@router.patch("/{notebook_id}", response_model=NotebookOut)
def update_notebook(
    notebook_id: str,
    body: NotebookUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    notebook = db.query(Notebook).filter(Notebook.id == notebook_id).first()
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")
    require_access(db, user, "notebook", notebook_id, "write")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(notebook, field, value)
    db.commit()
    db.refresh(notebook)
    return notebook


@router.delete("/{notebook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notebook(
    notebook_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    notebook = db.query(Notebook).filter(Notebook.id == notebook_id).first()
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")
    require_access(db, user, "notebook", notebook_id, "owner")

    # Clean up all permissions for this notebook and its entries
    entry_ids = [e.id for e in notebook.entries]
    if entry_ids:
        db.query(Permission).filter(
            Permission.resource_type == "entry",
            Permission.resource_id.in_(entry_ids),
        ).delete(synchronize_session=False)
    db.query(Permission).filter(
        Permission.resource_type == "notebook",
        Permission.resource_id == notebook_id,
    ).delete(synchronize_session=False)

    db.delete(notebook)
    db.commit()


def _notify_entry_version(db: Session, entry: Entry) -> None:
    recipient_ids = {
        row[0]
        for row in (
            db.query(Permission.subject_id)
            .filter(
                Permission.resource_type == "notebook",
                Permission.resource_id == entry.notebook_id,
            )
            .all()
        )
    }
    event = EntryVersionEvent(
        notebook_id=entry.notebook_id,
        entry_id=entry.id,
        version=entry.version,
        updated_at=entry.updated_at,
    )
    for user_id in recipient_ids:
        entry_event_hub.publish(user_id, event)


@router.post("/import-labo", response_model=LaboImportResult, status_code=status.HTTP_201_CREATED)
async def import_labo_notebook(
    file: UploadFile = File(...),
    notebook_id: str | None = Query(None, description="Target notebook for entry archives; ignored for notebook archives"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Import a Labo Archive (.zip).

    - **Notebook archive** (``kind == \"notebook\"``) — always creates a brand-new
      notebook; ``notebook_id`` is ignored.
    - **Entry archive** (``kind == \"entry\"``) — imports entries into the notebook
      specified by ``notebook_id`` (required for this case).
    """
    raw = await file.read()
    try:
        archive = read_labo_archive(raw)
    except (ValueError, Exception) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    manifest = archive["manifest"]
    att_files = archive["files"]

    kind = manifest.get("kind")

    if kind == "entry":
        # Delegate to entry-import logic: create entries in the target notebook.
        if not notebook_id:
            raise HTTPException(
                status_code=400,
                detail="notebook_id is required when importing an entry archive.",
            )
        require_access(db, user, "notebook", notebook_id, "write")
        entries_data = [manifest]
        target_notebook_id = notebook_id

    elif kind == "notebook":
        if notebook_id:
            # Merge into the specified existing notebook.
            existing = db.query(Notebook).filter(Notebook.id == notebook_id).first()
            if not existing:
                raise HTTPException(status_code=404, detail="Notebook not found")
            require_access(db, user, "notebook", notebook_id, "write")
            target_notebook_id = notebook_id
        else:
            # No target specified — create a new notebook.
            new_notebook = Notebook(
                author_id=user.id,
                title=manifest["title"],
                description=manifest.get("description", ""),
            )
            db.add(new_notebook)
            db.flush()
            perm = Permission(
                subject_id=user.id,
                resource_type="notebook",
                resource_id=new_notebook.id,
                access_level="owner",
            )
            db.add(perm)
            target_notebook_id = new_notebook.id
        entries_data = manifest.get("entries", [])
    else:
        raise HTTPException(status_code=400, detail=f"Unrecognised archive kind: {kind!r}")

    # Create entries (shared by both paths).
    created_entry_ids: list[str] = []

    for entry_data in entries_data:
        entry = Entry(
            notebook_id=target_notebook_id,
            author_id=user.id,
            title=entry_data["title"],
            content_blocks=entry_data.get("content_blocks", []),
            tags=entry_data.get("tags", []),
        )
        db.add(entry)
        db.flush()

        id_map: dict[str, str] = {}
        for att_meta in entry_data.get("attachments", []):
            old_id: str = att_meta["id"]
            file_info = att_files.get(old_id)
            if not file_info:
                continue

            entry_dir = settings.storage_dir / entry.id
            entry_dir.mkdir(parents=True, exist_ok=True)
            storage_path = entry_dir / file_info["filename"]
            storage_path.write_bytes(file_info["data"])

            attachment = Attachment(
                entry_id=entry.id,
                type=att_meta["type"],
                filename=att_meta["filename"],
                mime_type=att_meta["mime_type"],
                size=len(file_info["data"]),
                storage_uri=str(storage_path),
            )
            db.add(attachment)
            db.flush()
            id_map[old_id] = attachment.id

        if id_map:
            entry.content_blocks = _rewrite_attachment_urls(entry.content_blocks, id_map)

        created_entry_ids.append(entry.id)

    db.commit()

    for eid in created_entry_ids:
        entry_obj = db.query(Entry).filter(Entry.id == eid).first()
        if entry_obj:
            _notify_entry_version(db, entry_obj)

    return LaboImportResult(kind=kind, notebook_id=target_notebook_id, entry_ids=created_entry_ids)


@router.get("/{notebook_id}/export")
def export_notebook(
    notebook_id: str,
    format: str = Query("md", description="Export format: md, html, pdf, docx, latex, labo"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Export an entire notebook in the requested format.

    Each entry is rendered with its title as an H1 heading, separated by
    horizontal rules.
    """
    if format == "labo":
        notebook = db.query(Notebook).filter(Notebook.id == notebook_id).first()
        if not notebook:
            raise HTTPException(status_code=404, detail="Notebook not found")
        require_access(db, user, "notebook", notebook_id, "read")

        entries = (
            db.query(Entry)
            .filter(Entry.notebook_id == notebook_id)
            .order_by(Entry.updated_at.desc())
            .all()
        )
        entries_data = []
        for entry in entries:
            db_atts = db.query(Attachment).filter(Attachment.entry_id == entry.id).all()
            entries_data.append({
                "title": entry.title,
                "tags": entry.tags or [],
                "created_at": entry.created_at.isoformat(),
                "updated_at": entry.updated_at.isoformat(),
                "content_blocks": entry.content_blocks or [],
                "attachments": [
                    {
                        "id": a.id,
                        "filename": a.filename,
                        "mime_type": a.mime_type,
                        "type": a.type,
                        "storage_path": a.storage_uri,
                    }
                    for a in db_atts
                ],
            })
        data = export_labo_archive_notebook(
            notebook_title=notebook.title,
            notebook_description=notebook.description or "",
            notebook_created_at=notebook.created_at.isoformat(),
            notebook_updated_at=notebook.updated_at.isoformat(),
            entries=entries_data,
        )
        safe_title = notebook.title.replace(" ", "_")
        return Response(
            content=data,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{safe_title}.zip"'},
        )

    if format not in EXPORT_FORMATS:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")

    notebook = db.query(Notebook).filter(Notebook.id == notebook_id).first()
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")
    require_access(db, user, "notebook", notebook_id, "read")

    entries = (
        db.query(Entry)
        .filter(Entry.notebook_id == notebook_id)
        .order_by(Entry.updated_at.desc())
        .all()
    )

    entry_dicts = [
        {"title": e.title, "content_blocks": e.content_blocks or []}
        for e in entries
    ]

    md = notebook_to_markdown(entry_dicts)

    # Collect all attachments referenced in the markdown, which may include
    # attachments from entries outside this notebook.  Namespace by the
    # owning entry's title to avoid filename clashes in the export.
    entry_title_by_id = {e.id: e.title for e in entries}
    referenced_ids = collect_attachment_ids(md)
    db_attachments = (
        db.query(Attachment).filter(Attachment.id.in_(referenced_ids)).all()
        if referenced_ids
        else []
    )

    # For attachments belonging to entries outside this notebook, look up
    # their entry titles so they can be namespaced properly.
    missing_entry_ids = {
        a.entry_id for a in db_attachments if a.entry_id not in entry_title_by_id
    }
    if missing_entry_ids:
        external_entries = (
            db.query(Entry.id, Entry.title)
            .filter(Entry.id.in_(missing_entry_ids))
            .all()
        )
        entry_title_by_id.update({e.id: e.title for e in external_entries})

    att_infos = [
        AttachmentInfo(
            id=a.id,
            filename=a.filename,
            storage_path=Path(a.storage_uri),
            entry_title=entry_title_by_id.get(a.entry_id),
        )
        for a in db_attachments
    ]

    info = EXPORT_FORMATS[format]
    safe_title = notebook.title.replace(" ", "_")

    try:
        data, is_zip = export_document(md, format, safe_title, att_infos)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if is_zip:
        filename = safe_title + ".zip"
        mime = "application/zip"
    else:
        filename = safe_title + info["extension"]
        mime = info["mime"]

    return Response(
        content=data,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
