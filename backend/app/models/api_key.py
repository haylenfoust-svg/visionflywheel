"""API Key model (P1.3) — machine-to-machine credentials."""

from __future__ import annotations

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ApiKey(TimestampMixin, Base):
    __tablename__ = "api_keys"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    key_hint: Mapped[str | None] = mapped_column(String(32), nullable=True)  # last 6 chars of raw
    owner_user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    scopes: Mapped[str] = mapped_column(Text, default="", nullable=False)  # comma-separated
    expires_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    revoked_at: Mapped[object | None] = mapped_column(String(32), nullable=True)
    last_used_at: Mapped[object | None] = mapped_column(String(32), nullable=True)
    call_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    @property
    def scope_list(self) -> list[str]:
        return [s for s in (self.scopes or "").split(",") if s]

    def __repr__(self) -> str:
        return f"<ApiKey {self.name} hint={self.key_hint}>"
