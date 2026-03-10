from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.access import highest_shared_level, require_access, resolve_access, user_sharing_status
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import Entry, EntryRevision, Notebook, Permission, User
from app.schemas import EntryCreate, EntryImport, EntryOut, EntryRevisionOut, EntryUpdate
from app.services.markdown import blocks_to_markdown, markdown_to_blocks

router = APIRouter(prefix="/entries", tags=["entries"])


class MarkdownParseRequest(BaseModel):
    markdown: str


class MarkdownParseResponse(BaseModel):
    blocks: list[dict]
    title: str | None


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
    notebook_access = resolve_access(db, user, "notebook", notebook_id)

    if notebook_access:
        # User has notebook-level access → show all entries in the notebook
        entries = (
            db.query(Entry)
            .filter(Entry.notebook_id == notebook_id)
            .order_by(Entry.updated_at.desc())
            .all()
        )
    else:
        # User may have entry-level access to individual entries in this notebook
        entries = (
            db.query(Entry)
            .filter(
                Entry.notebook_id == notebook_id,
                Entry.id.in_(
                    db.query(Permission.resource_id).filter(
                        Permission.subject_id == user.id,
                        Permission.resource_type == "entry",
                    )
                ),
            )
            .order_by(Entry.updated_at.desc())
            .all()
        )
        if not entries:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

    result = []
    for entry in entries:
        out = EntryOut.model_validate(entry)
        out.sharing_level = user_sharing_status(db, user.id, entry.author_id, "entry", entry.id)
        result.append(out)
    return result


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

    # Only create a revision on explicit checkpoint saves.
    if body.checkpoint and body.content_blocks is not None:
        revision = EntryRevision(
            entry_id=entry.id,
            author_id=user.id,
            content_blocks=entry.content_blocks,
            change_summary=body.change_summary,
        )
        db.add(revision)

    for field, value in body.model_dump(
        exclude_unset=True, exclude={"change_summary", "checkpoint"}
    ).items():
        setattr(entry, field, value)
    db.commit()
    db.refresh(entry)
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
    db.commit()
    db.refresh(entry)
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
