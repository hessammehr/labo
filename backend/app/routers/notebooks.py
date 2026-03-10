from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.access import highest_shared_level, require_access, user_sharing_status
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import Entry, Notebook, Permission, User
from app.schemas import NotebookCreate, NotebookOut, NotebookUpdate

router = APIRouter(prefix="/notebooks", tags=["notebooks"])


@router.get("/", response_model=list[NotebookOut])
def list_notebooks(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role == "admin":
        notebooks = db.query(Notebook).all()
    else:
        # Notebooks the user has direct permission on
        direct_notebook_ids = (
            db.query(Permission.resource_id)
            .filter(
                Permission.subject_id == user.id,
                Permission.resource_type == "notebook",
            )
            .subquery()
        )

        # Notebooks containing entries the user has direct permission on
        entry_notebook_ids = (
            db.query(Entry.notebook_id)
            .filter(
                Entry.id.in_(
                    db.query(Permission.resource_id).filter(
                        Permission.subject_id == user.id,
                        Permission.resource_type == "entry",
                    )
                )
            )
            .subquery()
        )

        notebooks = (
            db.query(Notebook)
            .filter(
                Notebook.id.in_(direct_notebook_ids)
                | Notebook.id.in_(entry_notebook_ids)
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
