"""Correction log — APPEND ONLY (PRD FR-3.7).

Every user action on a detection is recorded here. Rows are never updated
or deleted; `action='undo'` rows record that a prior correction was reverted
and are themselves append-only.

Action vocabulary (PRD FR-3.1 ~ FR-3.6):
    confirm          - the detection is correct as-is
    relabel          - class_name changed
    false_positive   - the box should not exist (negative sample)
    adjust           - bbox coordinates changed
    add              - a new box was drawn by hand (detection_id is NULL)
    undo             - the referenced correction was reverted
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

ACTIONS = ("confirm", "relabel", "false_positive", "adjust", "add", "undo")


class Correction(TimestampMixin, Base):
    __tablename__ = "corrections"

    # NULL for action='add' — the box did not exist before
    detection_id: Mapped[int | None] = mapped_column(
        ForeignKey("detections.id", ondelete="SET NULL"), index=True, nullable=True
    )
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True, nullable=False)

    action: Mapped[str] = mapped_column(String(24), nullable=False, index=True)

    # JSON-encoded snapshots. For 'undo' the values are flipped (new_value
    # holds what the detection looked like before the undone action).
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    # For action='undo' — which correction row this entry reverts.
    undo_of: Mapped[int | None] = mapped_column(Integer, nullable=True)

    operator: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Correction {self.id} {self.action} det={self.detection_id}>"
