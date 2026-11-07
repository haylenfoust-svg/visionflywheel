"""ORM models — import this module to register all tables with `Base.metadata`."""

from app.models.api_key import ApiKey
from app.models.audit import AuditLog
from app.models.base import Base, TimestampMixin
from app.models.config import ConfigEntry
from app.models.correction import Correction
from app.models.dataset import DatasetExport, DatasetSample, TrainingRun
from app.models.detection import Detection
from app.models.feedback import FeedbackTicket
from app.models.rbac import (
    AccountLock,
    AuthSession,
    LoginAttempt,
    Organization,
    Permission,
    Role,
    RolePermission,
    Team,
    TeamMember,
    UserRole,
)
from app.models.task import Task
from app.models.user import User
from app.models.weight import Weight

__all__ = [
    "ApiKey",
    "Base",
    "TimestampMixin",
    "User",
    "ConfigEntry",
    "AuditLog",
    "Task",
    "Detection",
    "Weight",
    "Correction",
    "FeedbackTicket",
    "DatasetExport",
    "DatasetSample",
    "TrainingRun",
    "Organization",
    "Team",
    "TeamMember",
    "Role",
    "Permission",
    "RolePermission",
    "UserRole",
    "AuthSession",
    "LoginAttempt",
    "AccountLock",
]
