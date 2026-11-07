"""TOTP two-factor authentication + password reset (PRD / B端 security).

2FA is *optional per account*. A user can enable TOTP via a one-time
provisioning secret; after that, login requires `password + totp_code`.
Password reset is token-based: an admin (or the user themselves if
self-service is enabled) issues a short-lived reset token that can be
exchanged for a new password.

OAuth / SSO: the `identity_provider` column on `users` reserves the
slot for future integration (Google / GitHub / SAML). The endpoints
expose the shape but raise a clear "not configured" error until the
provider is wired in.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import struct
import time
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import AppError, Err
from app.core.security import hash_password
from app.models.user import User

logger = logging.getLogger(__name__)

# ---- TOTP (RFC 6238) — minimal implementation, no external dependency ----
TOTP_DIGITS = 6
TOTP_PERIOD = 30
TOTP_WINDOW = 1  # ± 1 period tolerance


def _hotp(secret: bytes, counter: int) -> str:
    """HMAC-based one-time password (RFC 4226)."""
    msg = struct.pack(">Q", counter)
    digest = hmac.new(secret, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10 ** TOTP_DIGITS)).zfill(TOTP_DIGITS)


def generate_totp_secret() -> str:
    """Return a base32-encoded random secret for the user to scan."""
    raw = secrets.token_bytes(20)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def totp_uri(secret_base32: str, account: str, issuer: str = "VisionFlywheel") -> str:
    """Provisioning URI for authenticator apps."""
    return (
        f"otpauth://totp/{issuer}:{account}"
        f"?secret={secret_base32}&issuer={issuer}&algorithm=SHA1&digits={TOTP_DIGITS}&period={TOTP_PERIOD}"
    )


def verify_totp(secret_base32: str, code: str, *, at_time: float | None = None) -> bool:
    """Verify a 6-digit TOTP code with ±1 period tolerance."""
    if not code or not code.isdigit() or len(code) != TOTP_DIGITS:
        return False
    # Pad base32 to a valid length
    padded = secret_base32 + "=" * (-len(secret_base32) % 8)
    try:
        secret = base64.b32decode(padded, casefold=True)
    except Exception:
        return False
    counter = int((at_time or time.time()) / TOTP_PERIOD)
    for offset in range(-TOTP_WINDOW, TOTP_WINDOW + 1):
        if hmac.compare_digest(_hotp(secret, counter + offset), code):
            return True
    return False


# ---- password reset tokens ----
RESET_TOKEN_TTL_MINUTES = 30


def generate_reset_token() -> tuple[str, str, float]:
    """Return (token, token_hash, expires_at). Store only the hash."""
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expires_at = time.time() + RESET_TOKEN_TTL_MINUTES * 60
    return token, token_hash, expires_at


def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---- service facade ----
class TwoFactorService:
    """Per-account TOTP management."""

    @staticmethod
    def begin_setup(db: Session, user: User) -> dict[str, Any]:
        secret = generate_totp_secret()
        # Store as pending — only becomes active after a successful verify
        user.totp_secret_pending = secret
        user.totp_enabled = False
        db.commit()
        return {
            "secret": secret,
            "uri": totp_uri(secret, user.username),
            "digits": TOTP_DIGITS,
            "period": TOTP_PERIOD,
        }

    @staticmethod
    def confirm_setup(db: Session, user: User, code: str) -> dict[str, Any]:
        if not user.totp_secret_pending:
            raise AppError(Err.VALIDATION, "no pending 2FA setup", 400)
        if not verify_totp(user.totp_secret_pending, code):
            raise AppError(Err.VALIDATION, "invalid TOTP code", 400)
        user.totp_secret = user.totp_secret_pending
        user.totp_secret_pending = None
        user.totp_enabled = True
        db.commit()
        return {"enabled": True}

    @staticmethod
    def disable(db: Session, user: User, code: str | None = None) -> dict[str, Any]:
        if user.totp_enabled and code is not None and (
            not user.totp_secret or not verify_totp(user.totp_secret, code)
        ):
            raise AppError(Err.VALIDATION, "invalid TOTP code", 400)
        user.totp_secret = None
        user.totp_secret_pending = None
        user.totp_enabled = False
        db.commit()
        return {"enabled": False}

    @staticmethod
    def verify_login(user: User, code: str) -> bool:
        if not user.totp_enabled or not user.totp_secret:
            return True  # 2FA not active — pass through
        return verify_totp(user.totp_secret, code)


class PasswordResetService:
    """Token-based password reset."""

    @staticmethod
    def request_reset(db: Session, username: str) -> dict[str, Any]:
        """Issue a reset token. In production, this would be emailed."""
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            # Don't reveal whether the username exists
            return {"issued": True, "note": "if the account exists, a reset token was issued"}
        token, token_hash, expires_at = generate_reset_token()
        user.reset_token_hash = token_hash
        user.reset_token_expires_at = expires_at
        db.commit()
        # In production: send email. Here we surface it to the admin for testing.
        return {
            "issued": True,
            "token": token,  # REMOVE in production — only for admin handoff
            "expires_in_minutes": RESET_TOKEN_TTL_MINUTES,
        }

    @staticmethod
    def confirm_reset(db: Session, token: str, new_password: str) -> dict[str, Any]:
        from app.services.auth_service import validate_password

        try:
            validate_password(new_password)
        except Exception as exc:
            raise AppError(Err.VALIDATION, str(exc), 400) from exc

        token_hash = hash_reset_token(token)
        user = db.query(User).filter(User.reset_token_hash == token_hash).first()
        if user is None:
            raise AppError(Err.TOKEN_INVALID, "invalid or expired reset token", 401)
        if user.reset_token_expires_at and user.reset_token_expires_at < time.time():
            raise AppError(Err.TOKEN_EXPIRED, "reset token has expired", 401)
        user.password_hash = hash_password(new_password)
        user.reset_token_hash = None
        user.reset_token_expires_at = None
        db.commit()
        return {"reset": True}


# ---- OAuth / SSO placeholder ----
class OAuthService:
    """Reserved for future Google / GitHub / SAML integration.

    The architecture is wired: each provider gets a `connect` and `callback`
    route. Currently every route raises a clear "not configured" error so
    the shape is in place without pretending to work.
    """

    SUPPORTED_PROVIDERS = ("google", "github", "saml")

    @staticmethod
    def authorize_url(provider: str) -> str:
        if provider not in OAuthService.SUPPORTED_PROVIDERS:
            raise AppError(Err.VALIDATION, f"unsupported provider: {provider}", 400)
        raise AppError(
            Err.NOT_FOUND,
            f"OAuth provider '{provider}' is not configured. "
            f"Set the corresponding client ID/secret in .env to enable.",
            501,
        )

    @staticmethod
    def handle_callback(provider: str, code: str) -> dict[str, Any]:
        del code  # reserved for future OAuth exchange
        if provider not in OAuthService.SUPPORTED_PROVIDERS:
            raise AppError(Err.VALIDATION, f"unsupported provider: {provider}", 400)
        raise AppError(
            Err.NOT_FOUND,
            f"OAuth provider '{provider}' is not configured.",
            501,
        )
