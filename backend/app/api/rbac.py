"""RBAC admin endpoints (B端-7): roles, permissions, orgs, teams, membership."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.envelope import EnvelopeRoute
from app.core.exceptions import AppError, Err
from app.models.rbac import (
    Organization,
    Permission,
    Role,
    RolePermission,
    Team,
    TeamMember,
    UserRole,
)
from app.models.user import User
from app.services.permission_catalog import CATEGORIES, PERMISSION_CATALOG
from app.services.permission_service import (
    get_user_permission_codes,
    require_permission,
)

router = APIRouter(tags=["rbac"], route_class=EnvelopeRoute)


# ---------------- permissions catalog ----------------
@router.get("/rbac/permissions")
def list_permissions(_: CurrentUser) -> dict[str, Any]:
    """Grouped permission catalog for the admin matrix UI."""
    grouped: dict[str, list[dict]] = {key: [] for key, _ in CATEGORIES}
    for p in PERMISSION_CATALOG:
        grouped.setdefault(p.category, []).append(
            {
                "code": p.code,
                "name": p.name,
                "category": p.category,
                "description": p.description,
            }
        )
    return {"categories": [{"key": k, "label": label} for k, label in CATEGORIES], "permissions": grouped}


@router.get("/rbac/my-permissions")
def my_permissions(user: CurrentUser, db: Session = Depends(get_db)) -> dict[str, Any]:
    codes = sorted(get_user_permission_codes(db, user))
    return {"codes": codes, "is_admin": user.role == "admin"}


# ---------------- roles ----------------
@router.get("/rbac/roles")
def list_roles(_: User = Depends(require_permission("role.read")), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.query(Role).order_by(Role.id).all()
    return [
        {
            "id": r.id,
            "code": r.code,
            "name": r.name,
            "description": r.description,
            "is_system": r.is_system,
            "is_active": r.is_active,
            "permissions": sorted({p.code for p in r.permissions}),
        }
        for r in rows
    ]


class RoleCreate(BaseModel):
    code: str = Field(min_length=2, max_length=64, pattern=r"^[a-z][a-z0-9_\-]+$")
    name: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=500)
    permission_codes: list[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None
    permission_codes: list[str] | None = None


@router.post("/rbac/roles", status_code=201)
def create_role(
    payload: RoleCreate,
    _: User = Depends(require_permission("role.write")),
    db: Session = Depends(get_db),
) -> dict:
    if db.query(Role).filter(Role.code == payload.code).first():
        raise AppError(Err.CONFLICT, f"role already exists: {payload.code}", 409)
    role = Role(code=payload.code, name=payload.name, description=payload.description, is_system=False)
    db.add(role)
    db.commit()
    db.refresh(role)
    _assign_permissions(db, role, payload.permission_codes)
    return {"id": role.id, "code": role.code, "name": role.name}


@router.put("/rbac/roles/{role_id}")
def update_role(
    role_id: int,
    payload: RoleUpdate,
    _: User = Depends(require_permission("role.write")),
    db: Session = Depends(get_db),
) -> dict:
    role = db.query(Role).filter(Role.id == role_id).first()
    if role is None:
        raise AppError(Err.NOT_FOUND, f"role not found: {role_id}", 404)
    if payload.name is not None:
        role.name = payload.name
    if payload.description is not None:
        role.description = payload.description
    if payload.is_active is not None:
        role.is_active = payload.is_active
    db.commit()
    if payload.permission_codes is not None:
        _assign_permissions(db, role, payload.permission_codes)
    db.refresh(role)
    return {"id": role.id, "code": role.code, "permissions": sorted({p.code for p in role.permissions})}


@router.delete("/rbac/roles/{role_id}", )
def delete_role(
    role_id: int,
    _: User = Depends(require_permission("role.delete")),
    db: Session = Depends(get_db),
) -> None:
    role = db.query(Role).filter(Role.id == role_id).first()
    if role is None:
        raise AppError(Err.NOT_FOUND, f"role not found: {role_id}", 404)
    if role.is_system:
        raise AppError(Err.CONFLICT, "system role cannot be deleted", 409)
    db.delete(role)
    db.commit()


def _assign_permissions(db: Session, role: Role, codes: list[str]) -> None:
    valid = {p.code: p.id for p in db.query(Permission).all()}
    keep = {valid[c] for c in codes if c in valid}
    existing = db.query(RolePermission).filter(RolePermission.role_id == role.id).all()
    existing_ids = {rp.permission_id for rp in existing}
    for pid in existing_ids - keep:
        db.query(RolePermission).filter(
            RolePermission.role_id == role.id, RolePermission.permission_id == pid
        ).delete()
    for pid in keep - existing_ids:
        db.add(RolePermission(role_id=role.id, permission_id=pid))
    db.commit()


# ---------------- user ↔ role assignment ----------------
class UserRoleAssign(BaseModel):
    role_code: str
    scope_type: str = Field(default="global", pattern=r"^(global|org|team)$")
    scope_id: int | None = None


@router.get("/rbac/users/{user_id}/roles")
def get_user_roles(
    user_id: int,
    _: User = Depends(require_permission("user.read")),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.query(UserRole).filter(UserRole.user_id == user_id).all()
    out = []
    for ur in rows:
        role = db.query(Role).filter(Role.id == ur.role_id).first()
        if role is None:
            continue
        out.append(
            {
                "role_id": role.id,
                "role_code": role.code,
                "role_name": role.name,
                "scope_type": ur.scope_type,
                "scope_id": ur.scope_id,
            }
        )
    return out


@router.post("/rbac/users/{user_id}/roles", status_code=201)
def assign_role(
    user_id: int,
    payload: UserRoleAssign,
    _: User = Depends(require_permission("user.role.assign")),
    db: Session = Depends(get_db),
) -> dict:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise AppError(Err.NOT_FOUND, f"user not found: {user_id}", 404)
    role = db.query(Role).filter(Role.code == payload.role_code).first()
    if role is None:
        raise AppError(Err.NOT_FOUND, f"role not found: {payload.role_code}", 404)
    existing = (
        db.query(UserRole)
        .filter(
            UserRole.user_id == user_id,
            UserRole.role_id == role.id,
            UserRole.scope_type == payload.scope_type,
            UserRole.scope_id == payload.scope_id,
        )
        .first()
    )
    if existing is None:
        db.add(
            UserRole(
                user_id=user_id,
                role_id=role.id,
                scope_type=payload.scope_type,
                scope_id=payload.scope_id,
            )
        )
        db.commit()
    return {"user_id": user_id, "role_code": role.code, "scope_type": payload.scope_type, "scope_id": payload.scope_id}


@router.delete("/rbac/users/{user_id}/roles/{role_id}", )
def unassign_role(
    user_id: int,
    role_id: int,
    _: User = Depends(require_permission("user.role.assign")),
    db: Session = Depends(get_db),
) -> None:
    db.query(UserRole).filter(UserRole.user_id == user_id, UserRole.role_id == role_id).delete()
    db.commit()


# ---------------- organizations ----------------
class OrgCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=2, max_length=64, pattern=r"^[a-z][a-z0-9_\-]+$")
    parent_id: int | None = None
    description: str | None = Field(default=None, max_length=500)


class OrgUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None
    parent_id: int | None = None


@router.get("/rbac/orgs")
def list_orgs(_: User = Depends(require_permission("org.read")), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.query(Organization).order_by(Organization.id).all()
    return [
        {
            "id": o.id,
            "name": o.name,
            "code": o.code,
            "parent_id": o.parent_id,
            "description": o.description,
            "is_active": o.is_active,
        }
        for o in rows
    ]


@router.post("/rbac/orgs", status_code=201)
def create_org(
    payload: OrgCreate,
    _: User = Depends(require_permission("org.write")),
    db: Session = Depends(get_db),
) -> dict:
    if db.query(Organization).filter(Organization.code == payload.code).first():
        raise AppError(Err.CONFLICT, f"org already exists: {payload.code}", 409)
    org = Organization(
        name=payload.name,
        code=payload.code,
        parent_id=payload.parent_id,
        description=payload.description,
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return {"id": org.id, "code": org.code, "name": org.name}


@router.put("/rbac/orgs/{org_id}")
def update_org(
    org_id: int,
    payload: OrgUpdate,
    _: User = Depends(require_permission("org.write")),
    db: Session = Depends(get_db),
) -> dict:
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org is None:
        raise AppError(Err.NOT_FOUND, f"org not found: {org_id}", 404)
    for field in ("name", "description", "is_active", "parent_id"):
        value = getattr(payload, field)
        if value is not None:
            setattr(org, field, value)
    db.commit()
    db.refresh(org)
    return {"id": org.id, "code": org.code, "name": org.name}


@router.delete("/rbac/orgs/{org_id}", )
def delete_org(
    org_id: int,
    _: User = Depends(require_permission("org.write")),
    db: Session = Depends(get_db),
) -> None:
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org is None:
        raise AppError(Err.NOT_FOUND, f"org not found: {org_id}", 404)
    db.delete(org)
    db.commit()


# ---------------- teams ----------------
class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=2, max_length=64, pattern=r"^[a-z][a-z0-9_\-]+$")
    org_id: int | None = None
    description: str | None = Field(default=None, max_length=500)


class TeamMemberAdd(BaseModel):
    user_id: int
    role: str = Field(default="member", pattern=r"^(owner|admin|member|viewer)$")


@router.get("/rbac/teams")
def list_teams(_: User = Depends(require_permission("team.read")), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.query(Team).order_by(Team.id).all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "code": t.code,
            "org_id": t.org_id,
            "description": t.description,
            "is_active": t.is_active,
            "member_count": db.query(TeamMember).filter(TeamMember.team_id == t.id).count(),
        }
        for t in rows
    ]


@router.post("/rbac/teams", status_code=201)
def create_team(
    payload: TeamCreate,
    _: User = Depends(require_permission("team.write")),
    db: Session = Depends(get_db),
) -> dict:
    team = Team(
        name=payload.name,
        code=payload.code,
        org_id=payload.org_id,
        description=payload.description,
    )
    db.add(team)
    db.commit()
    db.refresh(team)
    return {"id": team.id, "code": team.code, "name": team.name}


@router.get("/rbac/teams/{team_id}/members")
def team_members(
    team_id: int,
    _: User = Depends(require_permission("team.read")),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.query(TeamMember).filter(TeamMember.team_id == team_id).all()
    out = []
    for tm in rows:
        user = db.query(User).filter(User.id == tm.user_id).first()
        if user is None:
            continue
        out.append(
            {
                "user_id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "role": tm.role,
            }
        )
    return out


@router.post("/rbac/teams/{team_id}/members", status_code=201)
def add_team_member(
    team_id: int,
    payload: TeamMemberAdd,
    _: User = Depends(require_permission("team.write")),
    db: Session = Depends(get_db),
) -> dict:
    team = db.query(Team).filter(Team.id == team_id).first()
    if team is None:
        raise AppError(Err.NOT_FOUND, f"team not found: {team_id}", 404)
    user = db.query(User).filter(User.id == payload.user_id).first()
    if user is None:
        raise AppError(Err.NOT_FOUND, f"user not found: {payload.user_id}", 404)
    existing = (
        db.query(TeamMember)
        .filter(TeamMember.team_id == team_id, TeamMember.user_id == payload.user_id)
        .first()
    )
    if existing is not None:
        existing.role = payload.role
    else:
        db.add(TeamMember(team_id=team_id, user_id=payload.user_id, role=payload.role))
    db.commit()
    return {"team_id": team_id, "user_id": payload.user_id, "role": payload.role}


@router.delete("/rbac/teams/{team_id}/members/{user_id}", )
def remove_team_member(
    team_id: int,
    user_id: int,
    _: User = Depends(require_permission("team.write")),
    db: Session = Depends(get_db),
) -> None:
    db.query(TeamMember).filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id).delete()
    db.commit()


# ---------------- categories (for the matrix UI) ----------------
@router.get("/rbac/categories")
def list_categories(_: CurrentUser) -> list[dict]:
    return [{"key": k, "label": label} for k, label in CATEGORIES]
