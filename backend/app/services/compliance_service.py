"""Compliance & data governance (P3.1).

Covers the four B端 compliance requirements:

1. **PII handling statement** — every upload triggers an implicit consent
   record; the privacy policy text is served from `/api/compliance/privacy`.
2. **Right to deletion** — a user (or admin) can request account deletion;
   the service cascades through uploads / detections / corrections /
   feedback / api_keys and issues an audit record.
3. **Audit export** — full audit trail exportable as CSV or JSON for
   external compliance review.
4. **RAG content safety** — knowledge entries are screened for PII and
   banned words before they enter the vector store.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import AppError, Err
from app.models.audit import AuditLog
from app.models.correction import Correction
from app.models.detection import Detection
from app.models.feedback import FeedbackTicket
from app.models.task import Task
from app.models.user import User

logger = logging.getLogger(__name__)

# ---- PII / banned-word patterns (extensible via config) ----
_PII_PATTERNS = [
    (r"\b\d{3}-\d{2}-\d{4}\b", "US SSN"),
    (r"\b\d{15,19}\b", "credit-card-like"),
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "email"),
    (r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", "phone-like"),
]

_BANNED_WORDS = {
    "hate", "violence", "self-harm", "illegal",
    # Extend via config: compliance_banned_words
}

PRIVACY_POLICY_VERSION = "1.0"
PRIVACY_POLICY_UPDATED = "2026-11-07"


def get_privacy_policy() -> dict[str, Any]:
    return {
        "version": PRIVACY_POLICY_VERSION,
        "updated": PRIVACY_POLICY_UPDATED,
        "sections": [
            {
                "id": "data_collected",
                "title": "我们收集的数据",
                "body": (
                    "为提供图像识别服务，我们处理你上传的图片及其派生的检测结果。"
                    "为提供智能问答服务，我们会记录你的提问与知识库内容。"
                    "我们不会将这些数据用于模型训练之外的用途，也不会向第三方出售。"
                ),
            },
            {
                "id": "data_usage",
                "title": "数据用途",
                "body": (
                    "1) 提供图像识别与校正服务；\n"
                    "2) 生成导出的 YOLO 训练集（仅用于你自己的模型训练）；\n"
                    "3) 智能问答（基于你自己的数据做检索增强）；\n"
                    "4) 系统审计与合规追溯。"
                ),
            },
            {
                "id": "retention",
                "title": "保存期限",
                "body": (
                    "默认长期保存，直到你主动删除。"
                    "导出的训练集与模型权重是你的资产，可随时下载与删除。"
                ),
            },
            {
                "id": "deletion",
                "title": "数据删除权",
                "body": (
                    "你随时可以在「系统管理 → 用户」页面删除账号，"
                    "或联系管理员发起删除请求。删除后，你的所有上传/检测/校正/工单"
                    "将被彻底清除（含审计记录），不可恢复。"
                ),
            },
            {
                "id": "security",
                "title": "安全措施",
                "body": (
                    "密码使用 bcrypt 哈希存储；"
                    "传输层使用 HTTPS；"
                    "支持 TOTP 两步验证；"
                    "API Key 仅存储 SHA-256 哈希。"
                ),
            },
        ],
    }


def detect_pii(text: str) -> list[dict[str, Any]]:
    """Scan text for PII patterns (used by RAG content safety)."""
    findings: list[dict[str, Any]] = []
    for pattern, label in _PII_PATTERNS:
        for match in re.finditer(pattern, text):
            findings.append({"kind": label, "match": match.group()[:20], "span": match.span()})
    return findings


def screen_content(text: str) -> dict[str, Any]:
    """Screen text before it enters the RAG knowledge base.

    Returns a verdict dict. `safe=False` means the entry should be rejected.
    """
    findings = detect_pii(text)
    banned_hits = [w for w in _BANNED_WORDS if w.lower() in text.lower()]
    safe = not findings and not banned_hits
    return {
        "safe": safe,
        "pii_findings": findings,
        "banned_hits": banned_hits,
        "reason": None if safe else "content contains PII or banned words",
    }


# ---------- data deletion (right to be forgotten) ----------
def delete_user_data(db: Session, username: str, *, operator: str | None = None, hard_delete_user: bool = True) -> dict[str, Any]:
    """Cascade-delete all data owned by `username` and record an audit entry."""
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise AppError(Err.NOT_FOUND, f"user not found: {username}", 404)

    deleted: dict[str, int] = {}

    # Tasks owned by the user -> cascade to detections + corrections
    tasks = db.query(Task).filter(Task.created_by == username).all()
    task_ids = [t.id for t in tasks]
    if task_ids:
        n_det = db.query(Detection).filter(Detection.task_id.in_(task_ids)).delete(synchronize_session=False)
        n_corr = db.query(Correction).filter(Correction.task_id.in_(task_ids)).delete(synchronize_session=False)
        deleted["detections"] = n_det
        deleted["corrections"] = n_corr
    n_tasks = db.query(Task).filter(Task.created_by == username).delete(synchronize_session=False)
    deleted["tasks"] = n_tasks

    # Feedback tickets
    n_fb = db.query(FeedbackTicket).filter(FeedbackTicket.username == username).delete(synchronize_session=False)
    deleted["feedback_tickets"] = n_fb

    # Audit entries by the user
    n_audit = db.query(AuditLog).filter(AuditLog.operator == username).delete(synchronize_session=False)
    deleted["audit_logs"] = n_audit

    # API keys owned by the user
    try:
        from app.models.api_key import ApiKey

        n_keys = db.query(ApiKey).filter(ApiKey.owner_user_id == user.id).delete(synchronize_session=False)
        deleted["api_keys"] = n_keys
    except Exception:
        pass

    # Finally the user row
    if hard_delete_user:
        db.delete(user)
        deleted["user"] = 1
    else:
        user.is_active = False
        deleted["user"] = 0

    # Record a tombstone audit entry (does not delete itself)
    db.add(
        AuditLog(
            entity="compliance",
            entity_key=f"delete:{username}",
            old_value=json.dumps({"username": username}),
            new_value=json.dumps({"deleted": deleted, "hard": hard_delete_user}),
            operator=operator,
            action="delete",
        )
    )
    db.commit()
    logger.info("user data deleted: %s -> %s", username, deleted)
    return {"username": username, "deleted": deleted, "hard": hard_delete_user}


# ---------- audit export ----------
def export_audit(
    db: Session,
    *,
    entity: str | None = None,
    operator: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 10000,
    fmt: str = "csv",
) -> dict[str, Any]:
    """Export the audit trail as CSV or JSON for compliance review."""
    q = db.query(AuditLog)
    if entity:
        q = q.filter(AuditLog.entity == entity)
    if operator:
        q = q.filter(AuditLog.operator == operator)
    if start:
        q = q.filter(AuditLog.created_at >= start)
    if end:
        q = q.filter(AuditLog.created_at < end)
    rows = q.order_by(AuditLog.id.desc()).limit(limit).all()
    records = [
        {
            "id": r.id,
            "ts": r.created_at.isoformat() if r.created_at else None,
            "entity": r.entity,
            "entity_key": r.entity_key,
            "action": r.action,
            "operator": r.operator,
            "old_value": r.old_value,
            "new_value": r.new_value,
        }
        for r in rows
    ]

    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=["id", "ts", "entity", "entity_key", "action", "operator", "old_value", "new_value"])
        writer.writeheader()
        writer.writerows(records)
        return {
            "format": "csv",
            "count": len(records),
            "filename": f"audit-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.csv",
            "content": buf.getvalue(),
        }

    return {
        "format": "json",
        "count": len(records),
        "filename": f"audit-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json",
        "content": json.dumps(records, ensure_ascii=False, indent=2),
    }


# ---------- upload consent record ----------
def record_upload_consent(db: Session, username: str, filename: str, size_bytes: int) -> None:
    """Record an implicit consent entry when an image is uploaded (PII disclosure)."""
    db.add(
        AuditLog(
            entity="compliance",
            entity_key=f"upload:{filename}",
            old_value=None,
            new_value=json.dumps({"username": username, "size_bytes": size_bytes, "consent": "implicit_upload"}),
            operator=username,
            action="upload_consent",
        )
    )
    db.commit()
