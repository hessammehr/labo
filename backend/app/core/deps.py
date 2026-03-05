from datetime import datetime, timezone

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import hash_api_key
from app.models import ApiKey, Session, User


def get_current_user(
    db: DbSession = Depends(get_db),
    session_cookie: str | None = Cookie(None, alias=settings.session_cookie_name),
    x_api_key: str | None = Header(None),
) -> User:
    """Resolve the current user from session cookie or API key header."""
    user: User | None = None

    # 1. Try session cookie
    if session_cookie:
        session = db.query(Session).filter(Session.id == session_cookie).first()
        if session:
            now = datetime.now(timezone.utc)
            if session.expires_at.tzinfo is None:
                expires = session.expires_at.replace(tzinfo=timezone.utc)
            else:
                expires = session.expires_at
            if expires > now:
                user = session.user
            else:
                # Expired — clean up
                db.delete(session)
                db.commit()

    # 2. Try API key header
    if user is None and x_api_key:
        key_hash = hash_api_key(x_api_key)
        api_key = db.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()
        if api_key:
            user = api_key.user
            # Update last-used timestamp
            api_key.last_used_at = datetime.now(timezone.utc)
            db.commit()

    if user is None or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return user
