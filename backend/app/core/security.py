"""Password hashing and JWT helpers (PRD FR-1)."""

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    *,
    subject: str,
    role: str,
    expires_minutes: int | None = None,
    session_id: str | None = None,
    jti: str | None = None,
) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expire_delta = timedelta(minutes=expires_minutes or settings.access_token_expire_minutes)
    payload = {
        "sub": subject,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + expire_delta).timestamp()),
    }
    if session_id is not None:
        payload["sid"] = session_id
    if jti is not None:
        payload["jti"] = jti
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT. Raises `JWTError` on any failure."""
    settings = get_settings()
    return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])


class TokenError(Exception):
    """Wraps JWTError with a user-facing reason."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def safe_decode(token: str) -> dict:
    """Decode a token, converting library errors into `TokenError`."""
    try:
        return decode_access_token(token)
    except JWTError as exc:
        raise TokenError(str(exc)) from exc
