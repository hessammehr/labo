from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import Entry, EntryRevision, Notebook, Permission, User
from app.schemas import EntryCreate, EntryOut, EntryRevisionOut, EntryUpdate
from app.services.markdown import blocks_to_markdown

router = APIRouter(prefix="/entries", tags=["entries"])


def _can_access_notebook(
    db: Session,
    user: User,
    notebook_id: str,
    level: str = "read",
) -> Notebook:
    notebook = db.query(Notebook).filter(Notebook.id == notebook_id).first()
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")

    if notebook.owner_id == user.id or user.role == "admin":
        return notebook

    levels = {"read": 0, "write": 1, "admin": 2}
    perm = (
        db.query(Permission)
        .filter(
            Permission.subject_id == user.id,
            Permission.resource_type == "notebook",
            Permission.resource_id == notebook_id,
        )
        .first()
    )
    if not perm or levels.get(perm.access_level, -1) < levels[level]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return notebook


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

    # Check entry-level permission first, then notebook-level
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


@router.post("/", response_model=EntryOut, status_code=status.HTTP_201_CREATED)
def create_entry(
    body: EntryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _can_access_notebook(db, user, body.notebook_id, level="write")

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


@router.get("/notebook/{notebook_id}", response_model=list[EntryOut])
def list_entries_for_notebook(
    notebook_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _can_access_notebook(db, user, notebook_id, level="read")
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
    return _can_access_entry(db, user, entry_id)


@router.get("/{entry_id}/markdown")
def get_entry_markdown(
    entry_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entry = _can_access_entry(db, user, entry_id)
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
    entry = _can_access_entry(db, user, entry_id, level="write")

    # If moving entry to another notebook, require write access there too.
    if body.notebook_id and body.notebook_id != entry.notebook_id:
        _can_access_notebook(db, user, body.notebook_id, level="write")

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
    entry = _can_access_entry(db, user, entry_id, level="admin")
    db.delete(entry)
    db.commit()


@router.post("/{entry_id}/revisions/{revision_id}/restore", response_model=EntryOut)
def restore_revision(
    entry_id: str,
    revision_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entry = _can_access_entry(db, user, entry_id, level="write")

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
    _can_access_entry(db, user, entry_id)
    return (
        db.query(EntryRevision)
        .filter(EntryRevision.entry_id == entry_id)
        .order_by(EntryRevision.created_at.desc())
        .all()
    )
