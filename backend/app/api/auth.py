"""Auth endpoints (PRD FR-1, B端-3/4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import AdminUser, CurrentUser
from app.core.envelope import EnvelopeRoute
from app.core.exceptions import AppError, Err
from app.core.security import hash_password
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenOut, UserCreate, UserOut, UserUpdate
from app.services import auth_service
from app.services.permission_service import require_permission

router = APIRouter(prefix="/auth", tags=["auth"], route_class=EnvelopeRoute)


def _client_info(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    return ip, ua


# ---------------- login / refresh / logout ----------------
class LoginRequestExt(LoginRequest):
    device: str | None = Field(default=None, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10, max_length=256)


@router.post("/login", response_model=TokenOut)
def login(payload: LoginRequestExt, request: Request, db: Session = Depends(get_db)) -> TokenOut:
    ip, ua = _client_info(request)
    user, tokens = auth_service.login(
        db,
        username=payload.username,
        password=payload.password,
        ip_address=ip,
        user_agent=ua,
        device=payload.device,
    )
    return TokenOut(
        access_token=tokens.access_token,
        token_type="bearer",
        expires_in=tokens.expires_in,
        user=UserOut.model_validate(user),
    )


@router.post("/refresh")
def refresh(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    ip, _ = _client_info(request)
    tokens = auth_service.refresh_tokens(db, payload.refresh_token, ip_address=ip)
    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": "bearer",
        "expires_in": tokens.expires_in,
        "session_id": tokens.session_id,
    }


@router.post("/logout")
def logout(
    user: CurrentUser,
    db: Session = Depends(get_db),
    session_id: str | None = None,
) -> dict:
    if session_id:
        revoked = auth_service.revoke_session(db, session_id, reason="logout")
    else:
        auth_service.revoke_all_sessions(db, user.id, reason="logout")
        revoked = True
    return {"revoked": revoked}


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


# ---------------- users ----------------
@router.get("/users", response_model=list[UserOut])
def list_users(
    _: User = Depends(require_permission("user.read")),
    db: Session = Depends(get_db),
) -> list[UserOut]:
    users = db.query(User).order_by(User.id).all()
    return [UserOut.model_validate(u) for u in users]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate,
    _: User = Depends(require_permission("user.write")),
    db: Session = Depends(get_db),
) -> UserOut:
    try:
        auth_service.validate_password(payload.password)
    except auth_service.PasswordPolicyError as exc:
        raise AppError(Err.VALIDATION, str(exc), 400) from exc
    if db.query(User).filter(User.username == payload.username).first():
        raise AppError(Err.CONFLICT, f"username already exists: {payload.username}", 409)
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        display_name=payload.display_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    _: User = Depends(require_permission("user.write")),
    db: Session = Depends(get_db),
) -> UserOut:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise AppError(Err.NOT_FOUND, f"user not found: {user_id}", 404)
    if payload.password is not None:
        try:
            auth_service.validate_password(payload.password)
        except auth_service.PasswordPolicyError as exc:
            raise AppError(Err.VALIDATION, str(exc), 400) from exc
        user.password_hash = hash_password(payload.password)
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
        if not payload.is_active:
            # Force-revoke every session of the disabled user
            auth_service.revoke_all_sessions(db, user.id, reason="disabled")
    if payload.display_name is not None:
        user.display_name = payload.display_name
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.delete("/users/{user_id}", )
def delete_user(
    user_id: int,
    admin: AdminUser,
    db: Session = Depends(get_db),
) -> None:
    if user_id == admin.id:
        raise AppError(Err.CONFLICT, "cannot delete yourself", 409)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise AppError(Err.NOT_FOUND, f"user not found: {user_id}", 404)
    auth_service.revoke_all_sessions(db, user.id, reason="deleted")
    db.delete(user)
    db.commit()


# ---------------- sessions ----------------
@router.get("/sessions")
def my_sessions(user: CurrentUser, db: Session = Depends(get_db)) -> list[dict]:
    return auth_service.list_sessions(db, user_id=user.id)


@router.get("/sessions/all")
def all_sessions(
    _: User = Depends(require_permission("session.read")),
    db: Session = Depends(get_db),
) -> list[dict]:
    return auth_service.list_sessions(db)


@router.delete("/sessions/{session_id}", )
def revoke_one_session(
    session_id: str,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> None:
    from app.models.rbac import AuthSession

    session = db.query(AuthSession).filter(AuthSession.session_id == session_id).first()
    if session is None:
        raise AppError(Err.NOT_FOUND, f"session not found: {session_id}", 404)
    # Non-admins can only revoke their own sessions
    if session.user_id != user.id:
        has = require_permission("session.revoke")
        try:
            has(user=user, db=db)
        except AppError:
            raise
    auth_service.revoke_session(db, session_id, reason="admin")


# ---------------- login attempts ----------------
@router.get("/login-attempts")
def login_attempts(
    _: User = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db),
    username: str | None = None,
    limit: int = 50,
) -> list[dict]:
    return auth_service.list_login_attempts(db, username=username, limit=limit)
