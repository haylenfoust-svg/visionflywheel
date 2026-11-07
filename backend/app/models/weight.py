"""Weight model — registry of available YOLO checkpoints (PRD FR-6)."""

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Weight(TimestampMixin, Base):
    __tablename__ = "weights"

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # Path relative to the project root (e.g. backend/weights/best_v1.pt)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # manual | trained
    source: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    # dataset_version the checkpoint was trained on (PRD §8.3)
    dataset_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # holdout mAP measured at training time (PRD §8.2)
    holdout_map: Mapped[float | None] = mapped_column(nullable=True)
    class_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Weight {self.id} {self.filename} default={self.is_default}>"
