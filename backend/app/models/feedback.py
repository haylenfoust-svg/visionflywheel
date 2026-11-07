"""Feedback ticket — user → admin (PRD FR-4)."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class FeedbackTicket(TimestampMixin, Base):
    __tablename__ = "feedback_tickets"

    detection_id: Mapped[int | None] = mapped_column(
        ForeignKey("detections.id", ondelete="SET NULL"), index=True, nullable=True
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), index=True, nullable=True
    )

    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    username: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)

    content: Mapped[str] = mapped_column(Text, nullable=False)
    # open | replied | resolved | rejected
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False, index=True)

    reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    replied_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    def __repr__(self) -> str:
        return f"<FeedbackTicket {self.id} status={self.status}>"
