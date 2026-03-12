"""CRUD for scoped API tokens (create, list, update, revoke)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.access import require_access
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import generate_api_key, hash_api_key
from app.models import ScopedToken, User
from app.schemas import ScopedTokenCreate, ScopedTokenCreated, ScopedTokenOut, ScopedTokenUpdate

router = APIRouter(prefix="/scoped-tokens", tags=["scoped-tokens"])


@router.post("/", response_model=ScopedTokenCreated, status_code=status.HTTP_201_CREATED)
def create_token(
    body: ScopedTokenCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a scoped token. Requires owner-level access on the resource."""
    if body.resource_type not in ("notebook", "entry"):
        raise HTTPException(status_code=422, detail="resource_type must be 'notebook' or 'entry'")
    if body.access_level not in ("read", "readwrite"):
        raise HTTPException(status_code=422, detail="access_level must be 'read' or 'readwrite'")

    require_access(db, user, body.resource_type, body.resource_id, "owner")

    raw_token = generate_api_key()  # "labo_" + 48 hex chars
    token = ScopedToken(
        created_by=user.id,
        token_hash=hash_api_key(raw_token),
        token_prefix=raw_token[:12],
        label=body.label or "",
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        access_level=body.access_level,
    )
    db.add(token)
    db.commit()
    db.refresh(token)

    return ScopedTokenCreated(
        id=token.id,
        token_prefix=token.token_prefix,
        label=token.label,
        resource_type=token.resource_type,
        resource_id=token.resource_id,
        access_level=token.access_level,
        created_at=token.created_at,
        last_used_at=token.last_used_at,
        token=raw_token,
    )


@router.get("/resource/{resource_type}/{resource_id}", response_model=list[ScopedTokenOut])
def list_tokens(
    resource_type: str,
    resource_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List scoped tokens for a resource. Requires owner-level access."""
    require_access(db, user, resource_type, resource_id, "owner")

    tokens = (
        db.query(ScopedToken)
        .filter(
            ScopedToken.resource_type == resource_type,
            ScopedToken.resource_id == resource_id,
        )
        .order_by(ScopedToken.created_at.desc())
        .all()
    )
    return tokens


@router.patch("/{token_id}", response_model=ScopedTokenOut)
def update_token(
    token_id: str,
    body: ScopedTokenUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update a scoped token's access level or label."""
    token = db.query(ScopedToken).filter(ScopedToken.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    require_access(db, user, token.resource_type, token.resource_id, "owner")

    if body.access_level is not None:
        if body.access_level not in ("read", "readwrite"):
            raise HTTPException(status_code=422, detail="access_level must be 'read' or 'readwrite'")
        token.access_level = body.access_level
    if body.label is not None:
        token.label = body.label

    db.commit()
    db.refresh(token)
    return token


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_token(
    token_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Revoke (delete) a scoped token."""
    token = db.query(ScopedToken).filter(ScopedToken.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    require_access(db, user, token.resource_type, token.resource_id, "owner")

    db.delete(token)
    db.commit()
