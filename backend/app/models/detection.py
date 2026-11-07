"""Detection model — one bounding box on one image."""

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Detection(TimestampMixin, Base):
    __tablename__ = "detections"

    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True, nullable=False)
    # Position within a batch / video frame index. 0 for single-image tasks.
    item_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Paths are relative to runtime_data/ — never absolute
    image_path: Mapped[str] = mapped_column(String(512), nullable=False)
    result_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    class_id: Mapped[int] = mapped_column(Integer, nullable=False)
    class_name: Mapped[str] = mapped_column(String(64), nullable=False)  # English (canonical)
    class_name_zh: Mapped[str | None] = mapped_column(String(64), nullable=True)  # Chinese (display)

    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    x1: Mapped[float] = mapped_column(Float, nullable=False)
    y1: Mapped[float] = mapped_column(Float, nullable=False)
    x2: Mapped[float] = mapped_column(Float, nullable=False)
    y2: Mapped[float] = mapped_column(Float, nullable=False)

    # pending | corrected | rejected
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    # model | manual
    source: Mapped[str] = mapped_column(String(16), default="model", nullable=False)

    task: Mapped["Task"] = relationship("Task", back_populates="detections")  # noqa: F821

    @property
    def bbox(self) -> dict[str, float]:
        return {"x1": self.x1, "y1": self.y1, "x2": self.x2, "y2": self.y2}

    def __repr__(self) -> str:
        return f"<Detection {self.id} {self.class_name}@{self.confidence:.2f}>"
