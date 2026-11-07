"""Auth endpoints (PRD FR-1, docs/API.md §1)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import AdminUser, CurrentUser
from app.core.envelope import EnvelopeRoute
from app.core.exceptions import AppError, Err
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenOut, UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/auth", tags=["auth"], route_class=EnvelopeRoute)


@router.post("/login", response_model=TokenOut)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenOut:
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise AppError(Err.BAD_CREDENTIALS, "incorrect username or password", 401)
    if not user.is_active:
        raise AppError(Err.FORBIDDEN, "account disabled", 403)

    from app.core.config import get_settings

    expires = get_settings().access_token_expire_minutes
    token = create_access_token(subject=user.username, role=user.role, expires_minutes=expires)
    return TokenOut(access_token=token, expires_in=expires * 60, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.get("/users", response_model=list[UserOut])
def list_users(_: AdminUser, db: Session = Depends(get_db)) -> list[UserOut]:
    users = db.query(User).order_by(User.id).all()
    return [UserOut.model_validate(u) for u in users]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, _: AdminUser, db: Session = Depends(get_db)) -> UserOut:
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
def update_user(user_id: int, payload: UserUpdate, _: AdminUser, db: Session = Depends(get_db)) -> UserOut:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise AppError(Err.NOT_FOUND, f"user not found: {user_id}", 404)
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.display_name is not None:
        user.display_name = payload.display_name
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, admin: AdminUser, db: Session = Depends(get_db)) -> None:
    if user_id == admin.id:
        raise AppError(Err.CONFLICT, "cannot delete yourself", 409)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise AppError(Err.NOT_FOUND, f"user not found: {user_id}", 404)
    db.delete(user)
    db.commit()
