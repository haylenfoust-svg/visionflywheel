"""User model (PRD FR-1) — with 2FA / password-reset / OAuth fields."""

from sqlalchemy import Boolean, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="user", nullable=False)  # user | admin
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # --- TOTP two-factor (optional per-account) ---
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_secret_pending: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # --- password reset tokens ---
    reset_token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reset_token_expires_at: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- OAuth / SSO slot (google | github | saml) ---
    identity_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    identity_provider_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    def __repr__(self) -> str:
        return f"<User {self.username} role={self.role}>"
