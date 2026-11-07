"""Authentication service — JWT, refresh-token rotation, session registry,
login security (lockout + rate limit), password policy. (B端-3, B端-4)

Tokens
------
- access_token: short-lived JWT (default 30 min) — the only token sent to
  endpoints. Contains `sub` (username), `role`, `sid` (session id), `jti`.
- refresh_token: opaque random string (default 30 days) — sent only to
  `/api/auth/refresh` and `/api/auth/logout`. Stored hashed in
  `auth_sessions.refresh_hash`. Rotates on every refresh.

Session registry
----------------
Each login creates one `AuthSession` row. Refresh rotates `refresh_hash`
in-place (same `session_id`), so the audit trail is unbroken. Logout
revokes the row. Admins can list and revoke sessions.

Login security
--------------
- Failed attempts are recorded in `login_attempts`.
- 5 failures inside 15 minutes lock the account (recorded in
  `account_locks` so it survives a restart).
- Per-IP rate limit: 30 attempts / 5 minutes.
- Password policy: min 8 chars, at least 1 letter + 1 digit.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, Err
from app.core.security import (
    create_access_token,
    verify_password,
)
from app.models.rbac import (
    AccountLock,
    AuthSession,
    LoginAttempt,
)
from app.models.user import User

logger = logging.getLogger(__name__)

# ---- tunables (PRD B4) ----
MAX_FAILED_ATTEMPTS = 5
LOCK_DURATION_MINUTES = 15
RATE_LIMIT_ATTEMPTS = 30
RATE_LIMIT_WINDOW_MINUTES = 5
ACCESS_TOKEN_MINUTES = 30
REFRESH_TOKEN_DAYS = 30
PASSWORD_MIN_LENGTH = 8


# ---------------- password policy ----------------
class PasswordPolicyError(ValueError):
    pass


def validate_password(password: str) -> None:
    if len(password) < PASSWORD_MIN_LENGTH:
        raise PasswordPolicyError(f"密码至少 {PASSWORD_MIN_LENGTH} 位")
    if not any(c.isalpha() for c in password):
        raise PasswordPolicyError("密码必须包含字母")
    if not any(c.isdigit() for c in password):
        raise PasswordPolicyError("密码必须包含数字")


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------------- token helpers ----------------
@dataclass
class TokenPair:
    access_token: str
    refresh_token: str
    session_id: str
    expires_in: int  # seconds


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def issue_token_pair(
    db: Session,
    user: User,
    *,
    device: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    existing_session_id: str | None = None,
) -> TokenPair:
    """Create (or rotate) a session and return fresh tokens."""
    session_id = existing_session_id or uuid.uuid4().hex

    refresh_token = secrets.token_urlsafe(48)
    refresh_hash = hash_refresh_token(refresh_token)
    expires_at = _utcnow() + timedelta(days=REFRESH_TOKEN_DAYS)

    session = (
        db.query(AuthSession).filter(AuthSession.session_id == session_id).first()
        if existing_session_id
        else None
    )
    if session is None:
        session = AuthSession(
            user_id=user.id,
            session_id=session_id,
            refresh_hash=refresh_hash,
            device=device,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at,
            last_used_at=_utcnow(),
        )
        db.add(session)
    else:
        # Rotation: same session, new refresh token
        session.refresh_hash = refresh_hash
        session.expires_at = expires_at
        session.last_used_at = _utcnow()
        if device:
            session.device = device
        if ip_address:
            session.ip_address = ip_address

    db.commit()

    access_token = create_access_token(
        subject=user.username,
        role=user.role,
        expires_minutes=ACCESS_TOKEN_MINUTES,
        session_id=session_id,
        jti=uuid.uuid4().hex,
    )

    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        session_id=session_id,
        expires_in=ACCESS_TOKEN_MINUTES * 60,
    )


def refresh_tokens(
    db: Session,
    refresh_token: str,
    *,
    ip_address: str | None = None,
) -> TokenPair:
    """Exchange a refresh token for a new pair. Rotation is enforced."""
    refresh_hash = hash_refresh_token(refresh_token)
    session = db.query(AuthSession).filter(AuthSession.refresh_hash == refresh_hash).first()
    if session is None:
        raise AppError(Err.TOKEN_INVALID, "refresh token not recognised", 401)
    if not session.is_active:
        raise AppError(Err.TOKEN_EXPIRED, "session expired or revoked", 401)

    user = db.query(User).filter(User.id == session.user_id).first()
    if user is None or not user.is_active:
        raise AppError(Err.TOKEN_INVALID, "user not found or disabled", 401)

    return issue_token_pair(
        db,
        user,
        device=session.device,
        ip_address=ip_address or session.ip_address,
        user_agent=session.user_agent,
        existing_session_id=session.session_id,
    )


def revoke_session(db: Session, session_id: str, *, reason: str = "logout") -> bool:
    session = db.query(AuthSession).filter(AuthSession.session_id == session_id).first()
    if session is None or session.revoked_at is not None:
        return False
    session.revoked_at = _utcnow()
    session.revoked_reason = reason
    db.commit()
    return True


def revoke_all_sessions(db: Session, user_id: int, *, reason: str = "admin") -> int:
    sessions = (
        db.query(AuthSession)
        .filter(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .all()
    )
    for s in sessions:
        s.revoked_at = _utcnow()
        s.revoked_reason = reason
    db.commit()
    return len(sessions)


def list_sessions(db: Session, user_id: int | None = None, *, include_revoked: bool = False) -> list[dict[str, Any]]:
    q = db.query(AuthSession)
    if user_id is not None:
        q = q.filter(AuthSession.user_id == user_id)
    if not include_revoked:
        q = q.filter(AuthSession.revoked_at.is_(None))
    rows = q.order_by(AuthSession.last_used_at.desc().nullslast(), AuthSession.id.desc()).all()
    return [
        {
            "session_id": s.session_id,
            "user_id": s.user_id,
            "device": s.device,
            "ip_address": s.ip_address,
            "user_agent": s.user_agent,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "last_used_at": s.last_used_at.isoformat() if s.last_used_at else None,
            "expires_at": s.expires_at.isoformat() if s.expires_at else None,
            "is_active": s.is_active,
            "revoked_reason": s.revoked_reason,
        }
        for s in rows
    ]


# ---------------- login security ----------------
def _record_attempt(
    db: Session,
    *,
    username: str,
    ip_address: str | None,
    success: bool,
    failure_reason: str | None = None,
    user_agent: str | None = None,
) -> None:
    db.add(
        LoginAttempt(
            username=username,
            ip_address=ip_address,
            success=success,
            failure_reason=failure_reason,
            user_agent=user_agent,
        )
    )
    db.commit()


def _is_ip_rate_limited(db: Session, ip_address: str | None) -> bool:
    if not ip_address:
        return False
    window_start = _utcnow() - timedelta(minutes=RATE_LIMIT_WINDOW_MINUTES)
    count = (
        db.query(func.count(LoginAttempt.id))
        .filter(
            LoginAttempt.ip_address == ip_address,
            LoginAttempt.success.is_(False),
            LoginAttempt.created_at >= window_start,
        )
        .scalar()
        or 0
    )
    return count >= RATE_LIMIT_ATTEMPTS


def _check_and_update_lockout(db: Session, username: str) -> None:
    lock = db.query(AccountLock).filter(AccountLock.username == username).first()
    if lock is None:
        return
    if lock.locked_until and lock.locked_until > _utcnow():
        minutes = int((lock.locked_until - _utcnow()).total_seconds() // 60) + 1
        raise AppError(
            Err.FORBIDDEN,
            f"账号已被锁定，请 {minutes} 分钟后再试",
            403,
        )


def _register_failed_login(db: Session, username: str) -> None:
    lock = db.query(AccountLock).filter(AccountLock.username == username).first()
    if lock is None:
        lock = AccountLock(username=username, failed_count=0)
        db.add(lock)
    lock.failed_count = (lock.failed_count or 0) + 1
    if lock.failed_count >= MAX_FAILED_ATTEMPTS:
        lock.locked_until = _utcnow() + timedelta(minutes=LOCK_DURATION_MINUTES)
        lock.failed_count = 0
    db.commit()


def _reset_lockout(db: Session, username: str) -> None:
    lock = db.query(AccountLock).filter(AccountLock.username == username).first()
    if lock is not None:
        lock.failed_count = 0
        lock.locked_until = None
        db.commit()


# ---------------- public API ----------------
def login(
    db: Session,
    *,
    username: str,
    password: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
    device: str | None = None,
) -> tuple[User, TokenPair]:
    """Authenticate and issue tokens. Raises AppError on failure."""
    username = (username or "").strip()

    # Rate limit first (cheap)
    if _is_ip_rate_limited(db, ip_address):
        _record_attempt(
            db,
            username=username,
            ip_address=ip_address,
            success=False,
            failure_reason="rate_limited",
            user_agent=user_agent,
        )
        raise AppError(Err.FORBIDDEN, "尝试过于频繁，请稍后再试", 403)

    # Lockout
    _check_and_update_lockout(db, username)

    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        _record_attempt(
            db,
            username=username,
            ip_address=ip_address,
            success=False,
            failure_reason="bad_credentials",
            user_agent=user_agent,
        )
        _register_failed_login(db, username)
        raise AppError(Err.BAD_CREDENTIALS, "用户名或密码错误", 401)

    if not user.is_active:
        _record_attempt(
            db,
            username=username,
            ip_address=ip_address,
            success=False,
            failure_reason="disabled",
            user_agent=user_agent,
        )
        raise AppError(Err.FORBIDDEN, "账号已被禁用", 403)

    # Success
    _reset_lockout(db, username)
    _record_attempt(
        db,
        username=username,
        ip_address=ip_address,
        success=True,
        user_agent=user_agent,
    )
    tokens = issue_token_pair(
        db,
        user,
        device=device,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return user, tokens


def list_login_attempts(db: Session, *, username: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    q = db.query(LoginAttempt)
    if username:
        q = q.filter(LoginAttempt.username == username)
    rows = q.order_by(LoginAttempt.id.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "username": r.username,
            "ip_address": r.ip_address,
            "success": r.success,
            "failure_reason": r.failure_reason,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


def seed_permissions_and_roles(db: Session) -> dict[str, int]:
    """Idempotent seed of the permission catalog and default roles."""
    from app.models.rbac import Permission, Role, RolePermission
    from app.services.permission_catalog import (
        DEFAULT_ROLE_PERMISSIONS,
        DEFAULT_ROLES,
        PERMISSION_CATALOG,
    )

    created_perms = 0
    for spec in PERMISSION_CATALOG:
        exists = db.query(Permission).filter(Permission.code == spec.code).first()
        if exists is None:
            db.add(
                Permission(
                    code=spec.code,
                    name=spec.name,
                    category=spec.category,
                    description=spec.description,
                )
            )
            created_perms += 1
    db.commit()

    created_roles = 0
    for code, name, desc, is_system in DEFAULT_ROLES:
        role = db.query(Role).filter(Role.code == code).first()
        if role is None:
            role = Role(code=code, name=name, description=desc, is_system=is_system)
            db.add(role)
            db.commit()
            created_roles += 1

    # Assign permissions to roles
    for role_code, perm_codes in DEFAULT_ROLE_PERMISSIONS.items():
        role = db.query(Role).filter(Role.code == role_code).first()
        if role is None:
            continue
        existing = {
            rp.permission_id for rp in db.query(RolePermission).filter(RolePermission.role_id == role.id).all()
        }
        for code in perm_codes:
            perm = db.query(Permission).filter(Permission.code == code).first()
            if perm is None or perm.id in existing:
                continue
            db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.commit()

    return {"permissions_created": created_perms, "roles_created": created_roles}
