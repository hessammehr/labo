"""Centralised permission resolution with downward cascading.

Hierarchy: Notebook → Entry → Attachment
A user's effective access on a resource is the *highest* of:
  - direct permission on that resource, OR
  - inherited permission from the parent (recursively up the chain).

System admins bypass all checks.
"""

from sqlalchemy.orm import Session

from app.models import Attachment, Entry, Notebook, Permission, User

LEVELS = {"read": 0, "write": 1, "owner": 2}
LEVEL_NAMES = {v: k for k, v in LEVELS.items()}


def _direct_level(db: Session, user_id: str, resource_type: str, resource_id: str) -> int:
    """Return the numeric access level from a direct Permission row, or -1."""
    perm = (
        db.query(Permission)
        .filter(
            Permission.subject_id == user_id,
            Permission.resource_type == resource_type,
            Permission.resource_id == resource_id,
        )
        .first()
    )
    if perm:
        return LEVELS.get(perm.access_level, -1)
    return -1


def resolve_access(
    db: Session,
    user: User,
    resource_type: str,
    resource_id: str,
) -> str | None:
    """Return the effective access level name ('read'|'write'|'owner') or None.

    System admins always get 'owner'.
    """
    if user.role == "admin":
        return "owner"

    if resource_type == "notebook":
        level = _direct_level(db, user.id, "notebook", resource_id)
        return LEVEL_NAMES.get(level) if level >= 0 else None

    if resource_type == "entry":
        entry = db.query(Entry).filter(Entry.id == resource_id).first()
        if not entry:
            return None
        entry_level = _direct_level(db, user.id, "entry", resource_id)
        notebook_level = _direct_level(db, user.id, "notebook", entry.notebook_id)
        best = max(entry_level, notebook_level)
        return LEVEL_NAMES.get(best) if best >= 0 else None

    if resource_type == "attachment":
        att = db.query(Attachment).filter(Attachment.id == resource_id).first()
        if not att:
            return None
        return resolve_access(db, user, "entry", att.entry_id)

    return None


def require_access(
    db: Session,
    user: User,
    resource_type: str,
    resource_id: str,
    level: str = "read",
):
    """Raise 403 if user lacks the required access level."""
    from fastapi import HTTPException

    effective = resolve_access(db, user, resource_type, resource_id)
    if effective is None or LEVELS.get(effective, -1) < LEVELS[level]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")


def user_sharing_status(
    db: Session,
    user_id: str,
    author_id: str,
    resource_type: str,
    resource_id: str,
) -> str | None:
    """Return the sharing status of a notebook from the current user's perspective.

    Returns:
      - "shared_by_me" – current user is the original author and the notebook
        has been shared with at least one other person.
      - "read" / "write" / "owner" – current user is a recipient with that
        access level.
      - None – notebook is not shared (only the sole owner permission exists).
    """
    perms = (
        db.query(Permission)
        .filter(
            Permission.resource_type == resource_type,
            Permission.resource_id == resource_id,
        )
        .all()
    )

    # The creator always has a direct owner row; <= 1 means not shared.
    if len(perms) <= 1:
        return None

    if user_id == author_id:
        return "shared_by_me"

    user_perm = next((p for p in perms if p.subject_id == user_id), None)
    return user_perm.access_level if user_perm else None
