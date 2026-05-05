from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas import UserSearchResult

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserSearchResult])
def get_users_by_ids(
    ids: list[str] = Query(default=[]),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Look up users by id. Available to any authenticated user.

    Used for resolving author ids (e.g. on revisions) to display names,
    independent of any permission relationship to the requesting user.
    """
    if not ids:
        return []
    # De-duplicate to avoid wasted work on repeated ids.
    unique_ids = list({i for i in ids if i})
    if not unique_ids:
        return []
    return db.query(User).filter(User.id.in_(unique_ids)).all()
