"""Scope-aware query filter for org/team data isolation (B端-数据隔离).

Rules:
  - user has role='admin' (legacy) OR 'system.admin' permission  → no filter
  - user has a global-scope role                                → no filter
  - user has scoped role(s)                                     → filter by scope
  - otherwise (no role)                                         → only own rows

Model requirements: the model must expose `org_id` and `team_id` columns
(NULL-able) plus a `created_by` column for the fallback path.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Query, Session

from app.models.rbac import UserRole
from app.models.user import User

logger = logging.getLogger(__name__)


class ScopeFilter:
    """Describes which (scope_type, scope_id) pairs a user can see."""

    def __init__(self, *, is_global: bool, org_ids: set[int], team_ids: set[int], own_only: bool) -> None:
        self.is_global = is_global
        self.org_ids = org_ids
        self.team_ids = team_ids
        self.own_only = own_only

    def describe(self) -> dict[str, Any]:
        return {
            "is_global": self.is_global,
            "org_ids": sorted(self.org_ids),
            "team_ids": sorted(self.team_ids),
            "own_only": self.own_only,
        }


def get_user_scope_filter(db: Session, user: User) -> ScopeFilter:
    """Resolve the effective scope filter for `user`."""
    if user.role == "admin":
        return ScopeFilter(is_global=True, org_ids=set(), team_ids=set(), own_only=False)

    rows = db.query(UserRole).filter(UserRole.user_id == user.id).all()
    org_ids: set[int] = set()
    team_ids: set[int] = set()
    has_global = False
    for ur in rows:
        if ur.scope_type == "global":
            has_global = True
        elif ur.scope_type == "org" and ur.scope_id is not None:
            org_ids.add(ur.scope_id)
        elif ur.scope_type == "team" and ur.scope_id is not None:
            team_ids.add(ur.scope_id)

    if has_global:
        return ScopeFilter(is_global=True, org_ids=set(), team_ids=set(), own_only=False)

    if org_ids or team_ids:
        return ScopeFilter(is_global=False, org_ids=org_ids, team_ids=team_ids, own_only=False)

    # No RBAC role at all → only own rows
    return ScopeFilter(is_global=False, org_ids=set(), team_ids=set(), own_only=True)


def apply_scope_filter(query: Query, user: User, model: Any, db: Session) -> Query:
    """Constrain `query` to rows visible by `user` per the scope rules.

    `model` must have `org_id`, `team_id`, `created_by` columns (all nullable
    except `created_by`).
    """
    scope = get_user_scope_filter(db, user)
    if scope.is_global:
        return query

    conditions = []

    # Rows without scope (NULL org/team) are visible to anyone with any scope.
    conditions.append(
        (model.org_id.is_(None)) & (model.team_id.is_(None))
    )

    if scope.org_ids:
        conditions.append(model.org_id.in_(scope.org_ids))
    if scope.team_ids:
        conditions.append(model.team_id.in_(scope.team_ids))

    if scope.own_only:
        # No role → only own rows regardless of scope
        return query.filter(model.created_by == user.username)

    return query.filter(or_(*conditions))


def scope_meta(db: Session, user: User) -> dict[str, Any]:
    """Describe the user's scope for display in the UI / API metadata."""
    return get_user_scope_filter(db, user).describe()
