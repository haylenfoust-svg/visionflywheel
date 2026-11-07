"""Task model — one recognition run (single image, batch, or video)."""

from sqlalchemy import JSON, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"

    # image | batch | video
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    # pending | running | done | failed
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)

    created_by: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)

    # Inference parameters captured at run time (PRD FR-2.4)
    conf_threshold: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    iou_threshold: Mapped[float] = mapped_column(Float, default=0.45, nullable=False)
    imgsz: Mapped[int] = mapped_column(Integer, default=640, nullable=False)
    weight_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # What actually ran (yolo | fallback) — surfaced to UI per ADR-002
    detector_mode: Mapped[str] = mapped_column(String(16), default="yolo", nullable=False)

    total_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    done_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    inference_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    detections: Mapped[list["Detection"]] = relationship(  # noqa: F821
        "Detection",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="Detection.id",
    )

    def __repr__(self) -> str:
        return f"<Task {self.id} type={self.type} status={self.status}>"
