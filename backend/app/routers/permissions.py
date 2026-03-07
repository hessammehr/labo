from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.access import require_access
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import Permission, User
from app.schemas import PermissionCreate, PermissionDetail, PermissionOut, UserSearchResult

router = APIRouter(prefix="/permissions", tags=["permissions"])


@router.post("/", response_model=PermissionOut, status_code=status.HTTP_201_CREATED)
def grant_permission(
    body: PermissionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Grant or update a permission. Requires owner-level access on the resource."""
    require_access(db, user, body.resource_type, body.resource_id, "owner")

    # Validate subject exists
    subject = db.query(User).filter(User.id == body.subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="User not found")

    # Validate access_level
    if body.access_level not in ("read", "write", "owner"):
        raise HTTPException(status_code=422, detail="Invalid access level")

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
    """Revoke a permission. Requires owner-level access. Cannot remove the last owner."""
    perm = db.query(Permission).filter(Permission.id == permission_id).first()
    if not perm:
        raise HTTPException(status_code=404, detail="Permission not found")

    require_access(db, user, perm.resource_type, perm.resource_id, "owner")

    # Prevent removing the last owner
    if perm.access_level == "owner":
        owner_count = (
            db.query(Permission)
            .filter(
                Permission.resource_type == perm.resource_type,
                Permission.resource_id == perm.resource_id,
                Permission.access_level == "owner",
            )
            .count()
        )
        if owner_count <= 1:
            raise HTTPException(
                status_code=400,
                detail="Cannot remove the last owner",
            )

    db.delete(perm)
    db.commit()


@router.get("/resource/{resource_type}/{resource_id}", response_model=list[PermissionDetail])
def list_permissions(
    resource_type: str,
    resource_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List permissions for a resource with user info. Requires read access."""
    require_access(db, user, resource_type, resource_id, "read")

    perms = (
        db.query(Permission)
        .filter(
            Permission.resource_type == resource_type,
            Permission.resource_id == resource_id,
        )
        .all()
    )

    result = []
    for p in perms:
        u = db.query(User).filter(User.id == p.subject_id).first()
        result.append(
            PermissionDetail(
                id=p.id,
                subject_id=p.subject_id,
                subject_name=u.name if u else "Unknown",
                subject_email=u.email if u else "",
                resource_type=p.resource_type,
                resource_id=p.resource_id,
                access_level=p.access_level,
                created_at=p.created_at,
            )
        )
    return result


@router.get("/users/search", response_model=list[UserSearchResult])
def search_users(
    q: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Search users by name or email for the sharing modal."""
    pattern = f"%{q}%"
    return (
        db.query(User)
        .filter(User.status == "active")
        .filter(User.name.ilike(pattern) | User.email.ilike(pattern))
        .limit(10)
        .all()
    )
