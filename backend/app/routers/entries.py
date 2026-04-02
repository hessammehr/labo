from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import PlainTextResponse, Response
from pathlib import Path
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.access import require_access
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.events import EntryVersionEvent, entry_event_hub
from app.models import Attachment, Entry, EntryRevision, Notebook, Permission, User
from app.schemas import EntryCreate, EntryImport, EntryOut, EntryRevisionOut, EntryUpdate, LaboImportResult
from app.services.export import (
    EXPORT_FORMATS,
    AttachmentInfo,
    collect_attachment_ids,
    entry_to_markdown,
    export_document,
    export_labo_archive_entry,
    read_labo_archive,
    _rewrite_attachment_urls,
)
from app.services.markdown import blocks_to_markdown, markdown_to_blocks

router = APIRouter(prefix="/entries", tags=["entries"])


class MarkdownParseRequest(BaseModel):
    markdown: str


class MarkdownParseResponse(BaseModel):
    blocks: list[dict]
    title: str | None


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


@router.post("/", response_model=EntryOut, status_code=status.HTTP_201_CREATED)
def create_entry(
    body: EntryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_access(db, user, "notebook", body.notebook_id, "write")

    entry = Entry(
        notebook_id=body.notebook_id,
        author_id=user.id,
        title=body.title,
        content_blocks=body.content_blocks,
        tags=body.tags,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    _notify_entry_version(db, entry)
    return entry


@router.post("/import", response_model=EntryOut, status_code=status.HTTP_201_CREATED)
def import_markdown_entry(
    body: EntryImport,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Import a Markdown file as a new entry."""
    require_access(db, user, "notebook", body.notebook_id, "write")

    blocks, detected_title = markdown_to_blocks(body.markdown)
    title = detected_title or body.filename.removesuffix(".md").removesuffix(".markdown") or "Imported Entry"

    entry = Entry(
        notebook_id=body.notebook_id,
        author_id=user.id,
        title=title,
        content_blocks=blocks,
        tags=[],
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    _notify_entry_version(db, entry)
    return entry


@router.post("/parse-markdown", response_model=MarkdownParseResponse)
def parse_markdown(
    body: MarkdownParseRequest,
    _user: User = Depends(get_current_user),
):
    """Parse Markdown into BlockNote blocks without creating an entry."""
    blocks, title = markdown_to_blocks(body.markdown)
    return MarkdownParseResponse(blocks=blocks, title=title)


@router.get("/notebook/{notebook_id}", response_model=list[EntryOut])
def list_entries_for_notebook(
    notebook_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_access(db, user, "notebook", notebook_id, "read")
    return (
        db.query(Entry)
        .filter(Entry.notebook_id == notebook_id)
        .order_by(Entry.updated_at.desc())
        .all()
    )


@router.get("/{entry_id}", response_model=EntryOut)
def get_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entry = db.query(Entry).filter(Entry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    require_access(db, user, "entry", entry_id, "read")
    return entry


@router.get("/{entry_id}/markdown")
def get_entry_markdown(
    entry_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entry = db.query(Entry).filter(Entry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    require_access(db, user, "entry", entry_id, "read")
    md = blocks_to_markdown(entry.content_blocks or [], title=entry.title)
    filename = entry.title.replace(" ", "_") + ".md"
    return PlainTextResponse(
        content=md,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import-labo", response_model=LaboImportResult, status_code=status.HTTP_201_CREATED)
async def import_labo_entry(
    notebook_id: str = Query(..., description="Target notebook for imported entries"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Import a Labo Archive (.zip) as one or more entries in an existing notebook.

    Both entry archives and notebook archives are accepted; in either case
    the entries are created inside the specified notebook.
    """
    require_access(db, user, "notebook", notebook_id, "write")

    raw = await file.read()
    try:
        archive = read_labo_archive(raw)
    except (ValueError, Exception) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    manifest = archive["manifest"]
    att_files = archive["files"]

    kind = manifest.get("kind")
    if kind == "entry":
        entries_data = [manifest]
    elif kind == "notebook":
        entries_data = manifest.get("entries", [])
    else:
        raise HTTPException(status_code=400, detail=f"Unrecognised archive kind: {kind!r}")

    created_entry_ids: list[str] = []

    for entry_data in entries_data:
        entry = Entry(
            notebook_id=notebook_id,
            author_id=user.id,
            title=entry_data["title"],
            content_blocks=entry_data.get("content_blocks", []),
            tags=entry_data.get("tags", []),
        )
        db.add(entry)
        db.flush()  # obtain entry.id before writing attachments

        id_map: dict[str, str] = {}
        for att_meta in entry_data.get("attachments", []):
            old_id: str = att_meta["id"]
            file_info = att_files.get(old_id)
            if not file_info:
                continue  # file missing from archive — skip gracefully

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
            db.flush()  # obtain attachment.id for URL rewriting
            id_map[old_id] = attachment.id

        if id_map:
            entry.content_blocks = _rewrite_attachment_urls(entry.content_blocks, id_map)

        created_entry_ids.append(entry.id)

    db.commit()

    # Notify subscribers after committing so IDs are stable.
    for eid in created_entry_ids:
        entry_obj = db.query(Entry).filter(Entry.id == eid).first()
        if entry_obj:
            _notify_entry_version(db, entry_obj)

    return LaboImportResult(kind=kind, notebook_id=notebook_id, entry_ids=created_entry_ids)


@router.get("/{entry_id}/export")
def export_entry(
    entry_id: str,
    format: str = Query("md", description="Export format: md, html, pdf, docx, latex, labo"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Export an entry in the requested format."""
    if format == "labo":
        entry = db.query(Entry).filter(Entry.id == entry_id).first()
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found")
        require_access(db, user, "entry", entry_id, "read")

        db_attachments = (
            db.query(Attachment).filter(Attachment.entry_id == entry_id).all()
        )
        att_dicts = [
            {
                "id": a.id,
                "filename": a.filename,
                "mime_type": a.mime_type,
                "type": a.type,
                "storage_path": a.storage_uri,
            }
            for a in db_attachments
        ]
        data = export_labo_archive_entry(
            title=entry.title,
            content_blocks=entry.content_blocks or [],
            tags=entry.tags or [],
            created_at=entry.created_at.isoformat(),
            updated_at=entry.updated_at.isoformat(),
            attachments=att_dicts,
        )
        safe_title = entry.title.replace(" ", "_")
        return Response(
            content=data,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{safe_title}.zip"'},
        )

    if format not in EXPORT_FORMATS:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")

    entry = db.query(Entry).filter(Entry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    require_access(db, user, "entry", entry_id, "read")

    md = entry_to_markdown(entry.content_blocks or [], entry.title)

    # Collect all attachments referenced in the markdown, which may include
    # attachments belonging to other entries.
    referenced_ids = collect_attachment_ids(md)
    db_attachments = (
        db.query(Attachment).filter(Attachment.id.in_(referenced_ids)).all()
        if referenced_ids
        else []
    )

    # Attachments from this entry stay flat; those from other entries are
    # namespaced by their owning entry's title to prevent clashes.
    external_entry_ids = {
        a.entry_id for a in db_attachments if a.entry_id != entry_id
    }
    entry_title_by_id: dict[str, str] = {}
    if external_entry_ids:
        external_entries = (
            db.query(Entry.id, Entry.title)
            .filter(Entry.id.in_(external_entry_ids))
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
    safe_title = entry.title.replace(" ", "_")

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


@router.put("/{entry_id}", response_model=EntryOut)
def update_entry(
    entry_id: str,
    body: EntryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entry = db.query(Entry).filter(Entry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    require_access(db, user, "entry", entry_id, "write")

    # If moving entry to another notebook, require write access there too.
    if body.notebook_id and body.notebook_id != entry.notebook_id:
        require_access(db, user, "notebook", body.notebook_id, "write")

    incoming_fields = body.model_dump(
        exclude_unset=True,
        exclude={"change_summary", "checkpoint", "expected_version"},
    )

    # Only treat fields as changed if the value actually differs.
    changed_fields = {
        field: value
        for field, value in incoming_fields.items()
        if getattr(entry, field) != value
    }

    # Optimistic concurrency control: reject stale updates only when the
    # request would modify data. Stale no-op saves are accepted.
    if (
        changed_fields
        and body.expected_version is not None
        and body.expected_version != entry.version
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Entry was modified by someone else",
                "current_version": entry.version,
            },
        )

    # Only create a revision on explicit checkpoint saves that change content.
    if body.checkpoint and "content_blocks" in changed_fields:
        revision = EntryRevision(
            entry_id=entry.id,
            author_id=user.id,
            content_blocks=entry.content_blocks,
            change_summary=body.change_summary,
        )
        db.add(revision)

    for field, value in changed_fields.items():
        setattr(entry, field, value)

    if changed_fields:
        entry.version += 1

    db.commit()
    db.refresh(entry)
    if changed_fields:
        _notify_entry_version(db, entry)
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entry = db.query(Entry).filter(Entry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    require_access(db, user, "entry", entry_id, "owner")

    # Clean up entry-level permissions
    db.query(Permission).filter(
        Permission.resource_type == "entry",
        Permission.resource_id == entry_id,
    ).delete(synchronize_session=False)

    db.delete(entry)
    db.commit()


@router.post("/{entry_id}/revisions/{revision_id}/restore", response_model=EntryOut)
def restore_revision(
    entry_id: str,
    revision_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entry = db.query(Entry).filter(Entry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    require_access(db, user, "entry", entry_id, "write")

    revision = (
        db.query(EntryRevision)
        .filter(EntryRevision.id == revision_id, EntryRevision.entry_id == entry_id)
        .first()
    )
    if not revision:
        raise HTTPException(status_code=404, detail="Revision not found")

    # Checkpoint the current state before restoring so the user can undo.
    checkpoint = EntryRevision(
        entry_id=entry.id,
        author_id=user.id,
        content_blocks=entry.content_blocks,
        change_summary="Before restore",
    )
    db.add(checkpoint)

    entry.content_blocks = revision.content_blocks
    entry.version += 1
    db.commit()
    db.refresh(entry)
    _notify_entry_version(db, entry)
    return entry


@router.get("/{entry_id}/revisions", response_model=list[EntryRevisionOut])
def list_revisions(
    entry_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entry = db.query(Entry).filter(Entry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    require_access(db, user, "entry", entry_id, "read")
    return (
        db.query(EntryRevision)
        .filter(EntryRevision.entry_id == entry_id)
        .order_by(EntryRevision.created_at.desc())
        .all()
    )
