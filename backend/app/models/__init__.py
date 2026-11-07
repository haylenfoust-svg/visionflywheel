"""ORM models — import this module to register all tables with `Base.metadata`."""

from app.models.audit import AuditLog
from app.models.base import Base, TimestampMixin
from app.models.config import ConfigEntry
from app.models.detection import Detection
from app.models.task import Task
from app.models.user import User
from app.models.weight import Weight

__all__ = ["Base", "TimestampMixin", "User", "ConfigEntry", "AuditLog", "Task", "Detection", "Weight"]
