"""RBAC data model — roles, permissions, scopes (org/team), sessions.

Design:
  - permissions   fine-grained codes like "user.read", "dataset.export"
  - roles         named bundles of permissions (admin, operator, viewer)
  - role_permissions  M2M
  - user_roles    M2M with optional scope (global / org / team)
  - organizations  nested via parent_id
  - teams         belong to an org
  - team_members  user + role-in-team (owner/admin/member/viewer)
  - auth_sessions active refresh-token sessions (device, IP, revocation)
  - login_attempts  rate-limit + lockout bookkeeping

Scope semantics for user_roles:
  scope_type='global'  scope_id=NULL   → applies everywhere
  scope_type='org'     scope_id=<org>  → applies within that org
  scope_type='team'    scope_id=<team> → applies within that team
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    parent: Mapped[Organization | None] = relationship(
        "Organization", remote_side="Organization.id", back_populates="children"
    )
    children: Mapped[list[Organization]] = relationship("Organization", back_populates="parent")

    def __repr__(self) -> str:
        return f"<Organization {self.code}>"


class Team(TimestampMixin, Base):
    __tablename__ = "teams"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    org: Mapped[Organization | None] = relationship("Organization")

    def __repr__(self) -> str:
        return f"<Team {self.code}>"


class TeamMember(TimestampMixin, Base):
    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_user"),)

    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    # owner | admin | member | viewer
    role: Mapped[str] = mapped_column(String(16), default="member", nullable=False)

    team: Mapped[Team] = relationship("Team")
    user: Mapped[User] = relationship("User")  # noqa: F821

    def __repr__(self) -> str:
        return f"<TeamMember team={self.team_id} user={self.user_id} role={self.role}>"


class Role(TimestampMixin, Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # System roles cannot be deleted (admin / operator / viewer)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    permissions: Mapped[list[Permission]] = relationship(
        "Permission", secondary="role_permissions", back_populates="roles"
    )

    def __repr__(self) -> str:
        return f"<Role {self.code}>"


class Permission(TimestampMixin, Base):
    __tablename__ = "permissions"

    # e.g. "user.read", "dataset.export"
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # Grouping for the admin UI (user, task, dataset, weight, train, config, audit, system)
    category: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    roles: Mapped[list[Role]] = relationship(
        "Role", secondary="role_permissions", back_populates="permissions"
    )

    def __repr__(self) -> str:
        return f"<Permission {self.code}>"


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)

    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True, nullable=False
    )
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True, nullable=False
    )


class UserRole(TimestampMixin, Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", "scope_type", "scope_id", name="uq_user_role_scope"),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), index=True, nullable=False)
    # global | org | team
    scope_type: Mapped[str] = mapped_column(String(16), default="global", nullable=False)
    scope_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user: Mapped[User] = relationship("User")  # noqa: F821
    role: Mapped[Role] = relationship("Role")

    def __repr__(self) -> str:
        return f"<UserRole u={self.user_id} r={self.role_id} scope={self.scope_type}:{self.scope_id}>"


class AuthSession(TimestampMixin, Base):
    """One active login session (refresh-token family)."""

    __tablename__ = "auth_sessions"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    # Random identifier used to look up the refresh token family
    session_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    # SHA-256 hash of the current refresh token (never store raw tokens)
    refresh_hash: Mapped[str] = mapped_column(String(128), nullable=False)

    device: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)  # logout | rotate | admin

    user: Mapped[User] = relationship("User")  # noqa: F821

    @property
    def is_active(self) -> bool:
        from datetime import datetime, timezone

        if self.revoked_at is not None:
            return False
        if self.expires_at is None:
            return False
        now = datetime.now(timezone.utc)
        expires = self.expires_at
        if expires.tzinfo is None:
            from datetime import timezone as tz

            expires = expires.replace(tzinfo=tz.utc)
        return expires > now


class LoginAttempt(TimestampMixin, Base):
    """Rate-limit / lockout bookkeeping (PRD B4)."""

    __tablename__ = "login_attempts"

    username: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # failed | locked | rate_limited
    failure_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)


class AccountLock(TimestampMixin, Base):
    """Persisted account lockout state (survives restart)."""

    __tablename__ = "account_locks"

    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<AccountLock {self.username} failed={self.failed_count}>"
