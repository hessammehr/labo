from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import Notebook, Permission, User
from app.schemas import NotebookCreate, NotebookOut, NotebookUpdate

router = APIRouter(prefix="/notebooks", tags=["notebooks"])


def _can_access(db: Session, user: User, notebook_id: str, level: str = "read") -> Notebook:
    """Return notebook if user has at least `level` access, else 404/403."""
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


@router.get("/", response_model=list[NotebookOut])
def list_notebooks(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role == "admin":
        return db.query(Notebook).all()

    owned = db.query(Notebook).filter(Notebook.owner_id == user.id)
    shared = db.query(Notebook).filter(Notebook.id.in_(
        db.query(Permission.resource_id).filter(
            Permission.subject_id == user.id, Permission.resource_type == "notebook"
        )
    ))
    return owned.union(shared).all()


@router.post("/", response_model=NotebookOut, status_code=status.HTTP_201_CREATED)
def create_notebook(
    body: NotebookCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    notebook = Notebook(owner_id=user.id, title=body.title, description=body.description)
    db.add(notebook)
    db.commit()
    db.refresh(notebook)
    return notebook


@router.get("/{notebook_id}", response_model=NotebookOut)
def get_notebook(
    notebook_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _can_access(db, user, notebook_id)


@router.patch("/{notebook_id}", response_model=NotebookOut)
def update_notebook(
    notebook_id: str,
    body: NotebookUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    notebook = _can_access(db, user, notebook_id, level="write")
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
    notebook = _can_access(db, user, notebook_id, level="admin")
    if notebook.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Only owner or admin can delete")
    db.delete(notebook)
    db.commit()
