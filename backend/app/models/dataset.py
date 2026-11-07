"""Dataset export + holdout registry (PRD FR-5, §8.2)."""

from __future__ import annotations

from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class DatasetExport(TimestampMixin, Base):
    """One exported dataset snapshot. `dataset_version` is the immutable id."""

    __tablename__ = "dataset_exports"

    dataset_version: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(64), nullable=True)

    total_images: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_labels: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    train_images: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    val_images: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    holdout_images: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    class_names: Mapped[str] = mapped_column(Text, default="[]", nullable=False)  # JSON list
    val_ratio: Mapped[float] = mapped_column(Float, default=0.2, nullable=False)
    seed: Mapped[int] = mapped_column(Integer, default=42, nullable=False)

    # exporting | done | failed
    status: Mapped[str] = mapped_column(String(16), default="exporting", nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)  # relative to runtime_data/
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    def __repr__(self) -> str:
        return f"<DatasetExport {self.dataset_version} status={self.status}>"


class DatasetSample(TimestampMixin, Base):
    """Tracks each image's split assignment.

    `split` is set ONCE (train / val / holdout). Holdout images are frozen
    forever and never appear in training exports (PRD §8.2).
    """

    __tablename__ = "dataset_samples"

    image_path: Mapped[str] = mapped_column(String(512), unique=True, index=True, nullable=False)
    # train | val | holdout
    split: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    dataset_version: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    is_frozen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:
        return f"<DatasetSample {self.image_path} split={self.split}>"


class TrainingRun(TimestampMixin, Base):
    """One `yolo detect train` invocation (PRD FR-6)."""

    __tablename__ = "training_runs"

    dataset_version: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    base_weight: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(64), nullable=True)

    epochs: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    imgsz: Mapped[int] = mapped_column(Integer, default=640, nullable=False)
    batch: Mapped[int] = mapped_column(Integer, default=16, nullable=False)

    # pending | running | done | failed | cancelled
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)  # 0..1

    best_weight_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    holdout_map: Mapped[float | None] = mapped_column(Float, nullable=True)
    log_tail: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    def __repr__(self) -> str:
        return f"<TrainingRun {self.id} status={self.status}>"
