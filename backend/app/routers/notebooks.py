from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pathlib import Path
from sqlalchemy.orm import Session

from app.core.access import require_access, user_sharing_status
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import Attachment, Entry, Notebook, Permission, User
from app.schemas import NotebookCreate, NotebookOut, NotebookUpdate
from app.services.export import EXPORT_FORMATS, AttachmentInfo, export_document, notebook_to_markdown

router = APIRouter(prefix="/notebooks", tags=["notebooks"])


@router.get("/", response_model=list[NotebookOut])
def list_notebooks(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role == "admin":
        notebooks = db.query(Notebook).all()
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
    notebook = Notebook(author_id=user.id, title=body.title, description=body.description)
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


@router.get("/{notebook_id}/export")
def export_notebook(
    notebook_id: str,
    format: str = Query("md", description="Export format: md, html, pdf, docx, latex"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Export an entire notebook in the requested format.

    Each entry is rendered with its title as an H1 heading, separated by
    horizontal rules.
    """
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

    # Collect attachments across all entries in this notebook
    entry_ids = [e.id for e in entries]
    db_attachments = (
        db.query(Attachment)
        .filter(Attachment.entry_id.in_(entry_ids))
        .all()
    ) if entry_ids else []
    att_infos = [
        AttachmentInfo(id=a.id, filename=a.filename, storage_path=Path(a.storage_uri))
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
