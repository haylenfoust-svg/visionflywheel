"""2FA / password-reset / OAuth endpoints (PRD / B端 security)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.envelope import EnvelopeRoute
from app.services.permission_service import require_permission
from app.services.security_service import (
    OAuthService,
    PasswordResetService,
    TwoFactorService,
)

router = APIRouter(tags=["security"], route_class=EnvelopeRoute)


class TotpCode(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class PasswordResetRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=10, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# ---------- TOTP 2FA ----------
@router.post("/auth/2fa/setup")
def twofa_setup(user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    """Begin TOTP setup — returns the provisioning URI + secret."""
    return TwoFactorService.begin_setup(db, user)


@router.post("/auth/2fa/confirm")
def twofa_confirm(payload: TotpCode, user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    """Confirm the TOTP code and activate 2FA for this account."""
    return TwoFactorService.confirm_setup(db, user, payload.code)


@router.post("/auth/2fa/disable")
def twofa_disable(
    user: CurrentUser,
    db: Session = Depends(get_db),
    code: str | None = None,
) -> dict:
    """Disable 2FA. A TOTP code is required when 2FA is currently active."""
    return TwoFactorService.disable(db, user, code)


@router.get("/auth/2fa/status")
def twofa_status(user: CurrentUser) -> dict:
    return {
        "enabled": user.totp_enabled,
        "has_pending_setup": user.totp_secret_pending is not None,
    }


# ---------- Password reset ----------
@router.post("/auth/password-reset/request")
def password_reset_request(payload: PasswordResetRequest, db: Session = Depends(get_db)) -> dict:
    """Issue a reset token.

    In production this would be emailed to the user. Here it's returned in
    the response so an admin can hand it over during testing.
    """
    return PasswordResetService.request_reset(db, payload.username)


@router.post("/auth/password-reset/confirm")
def password_reset_confirm(payload: PasswordResetConfirm, db: Session = Depends(get_db)) -> dict:
    """Exchange a reset token for a new password."""
    return PasswordResetService.confirm_reset(db, payload.token, payload.new_password)


@router.post("/auth/password-reset/admin")
def admin_password_reset(
    payload: PasswordResetRequest,
    _admin: CurrentUser,
    db: Session = Depends(get_db),
    _perm: object = Depends(require_permission("user.write")),
) -> dict:
    """Admin-initiated password reset (returns the token for handoff)."""
    return PasswordResetService.request_reset(db, payload.username)


# ---------- OAuth / SSO placeholder ----------
@router.get("/auth/oauth/{provider}/authorize")
def oauth_authorize(provider: str) -> dict:
    """Redirect URL for the OAuth provider. Currently raises 501."""
    url = OAuthService.authorize_url(provider)
    return {"authorize_url": url}


@router.get("/auth/oauth/{provider}/callback")
def oauth_callback(provider: str, code: str, db: Session = Depends(get_db)) -> dict:
    """OAuth callback. Currently raises 501 — provider not configured."""
    return OAuthService.handle_callback(provider, code)
