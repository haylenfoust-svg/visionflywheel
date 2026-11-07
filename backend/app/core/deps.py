"""FastAPI dependencies: DB session, current user, role guard."""

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import AppError, Err
from app.core.security import TokenError, safe_decode
from app.models.user import User

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AppError(Err.TOKEN_INVALID, "missing bearer token", 401)
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = safe_decode(token)
    except TokenError as exc:
        raise AppError(Err.TOKEN_EXPIRED if "exp" in exc.reason else Err.TOKEN_INVALID, exc.reason, 401) from exc

    username = payload.get("sub")
    if not username:
        raise AppError(Err.TOKEN_INVALID, "token missing subject", 401)

    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise AppError(Err.TOKEN_INVALID, "user not found", 401)
    if not user.is_active:
        raise AppError(Err.FORBIDDEN, "account disabled", 403)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise AppError(Err.FORBIDDEN, "admin privilege required", 403)
    return user


AdminUser = Annotated[User, Depends(require_admin)]
