from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_admin
from app.models import Permission, User
from app.schemas import PermissionCreate, PermissionOut

router = APIRouter(prefix="/permissions", tags=["permissions"])


@router.post("/", response_model=PermissionOut, status_code=status.HTTP_201_CREATED)
def grant_permission(
    body: PermissionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Only resource owner or admin can grant permissions
    # Simplified check: admin can always grant; otherwise check ownership via resource
    if user.role != "admin":
        from app.models import Notebook, Entry

        if body.resource_type == "notebook":
            res = db.query(Notebook).filter(Notebook.id == body.resource_id).first()
            if not res or res.owner_id != user.id:
                raise HTTPException(status_code=403, detail="Only owner can share")
        elif body.resource_type == "entry":
            entry = db.query(Entry).filter(Entry.id == body.resource_id).first()
            if not entry:
                raise HTTPException(status_code=404, detail="Entry not found")
            nb = db.query(Notebook).filter(Notebook.id == entry.notebook_id).first()
            if not nb or nb.owner_id != user.id:
                raise HTTPException(status_code=403, detail="Only notebook owner can share entries")

    # Upsert: update if already exists
    existing = (
        db.query(Permission)
        .filter(
            Permission.subject_id == body.subject_id,
            Permission.resource_type == body.resource_type,
            Permission.resource_id == body.resource_id,
        )
        .first()
    )
    if existing:
        existing.access_level = body.access_level
        db.commit()
        db.refresh(existing)
        return existing

    perm = Permission(**body.model_dump())
    db.add(perm)
    db.commit()
    db.refresh(perm)
    return perm


@router.delete("/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_permission(
    permission_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    perm = db.query(Permission).filter(Permission.id == permission_id).first()
    if not perm:
        raise HTTPException(status_code=404, detail="Permission not found")

    if user.role != "admin":
        from app.models import Notebook

        if perm.resource_type == "notebook":
            nb = db.query(Notebook).filter(Notebook.id == perm.resource_id).first()
            if not nb or nb.owner_id != user.id:
                raise HTTPException(status_code=403, detail="Only owner can revoke")

    db.delete(perm)
    db.commit()


@router.get("/resource/{resource_type}/{resource_id}", response_model=list[PermissionOut])
def list_permissions(
    resource_type: str,
    resource_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return (
        db.query(Permission)
        .filter(
            Permission.resource_type == resource_type,
            Permission.resource_id == resource_id,
        )
        .all()
    )
