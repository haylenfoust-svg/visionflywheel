"""Permission enforcement (B端-2, B端-6).

Exposes `require_permission(...)` used as a FastAPI dependency. Resolves
the caller's effective permissions by unioning every role they hold
(global and scoped), then expanding `system.admin` to imply everything.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppError, Err
from app.models.rbac import Permission, RolePermission, UserRole
from app.models.user import User
from app.services.permission_catalog import (
    PERMISSION_INDEX,
    expand_permissions,
)

logger = logging.getLogger(__name__)


def get_user_permission_codes(
    db: Session,
    user: User,
    *,
    scope_type: str | None = None,
    scope_id: int | None = None,
) -> set[str]:
    """Union of permission codes from all the user's roles.

    When scope_type/scope_id are given, only roles matching that scope (or
    global roles) are considered. When they are omitted, every role is used.
    """
    query = (
        db.query(RolePermission.permission_id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .filter(UserRole.user_id == user.id)
    )
    if scope_type is not None:
        query = query.filter(
            (UserRole.scope_type == "global")
            | ((UserRole.scope_type == scope_type) & (UserRole.scope_id == scope_id))
        )

    perm_ids = [row[0] for row in query.distinct().all()]
    codes: set[str] = set()
    if perm_ids:
        for code, in db.query(Permission.code).filter(Permission.id.in_(perm_ids)).all():
            codes.add(code)
    return expand_permissions(codes)


def user_has_permission(
    db: Session,
    user: User,
    code: str,
    *,
    scope_type: str | None = None,
    scope_id: int | None = None,
) -> bool:
    if code not in PERMISSION_INDEX:
        logger.warning("unknown permission code checked: %s", code)
        return False
    codes = get_user_permission_codes(db, user, scope_type=scope_type, scope_id=scope_id)
    return code in codes


def require_permission(code: str) -> Callable:
    """FastAPI dependency factory: `Depends(require_permission('user.write'))`."""
    if code not in PERMISSION_INDEX:
        raise ValueError(f"unknown permission code: {code}")

    def _dep(user: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> User:
        # Legacy superusers (role field == 'admin') bypass checks during the
        # migration window so existing installs keep working.
        if user.role == "admin" or user_has_permission(db, user, code):
            return user
        raise AppError(
            Err.FORBIDDEN,
            f"missing permission: {code} ({PERMISSION_INDEX[code].name})",
            403,
        )

    return _dep


def require_any(*codes: str) -> Callable:
    """Dependency that requires ANY of the listed permissions."""
    for code in codes:
        if code not in PERMISSION_INDEX:
            raise ValueError(f"unknown permission code: {code}")

    def _dep(user: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> User:
        if user.role == "admin":
            return user
        user_codes = get_user_permission_codes(db, user)
        if any(c in user_codes for c in codes):
            return user
        raise AppError(
            Err.FORBIDDEN,
            f"missing permission: one of {list(codes)}",
            403,
        )

    return _dep
