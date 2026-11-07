"""Observability (P1.5) — structured logging, health, alert channels."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import get_settings

_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


class _StructuredFormatter(logging.Formatter):
    """Emit one JSON object per line for easy ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        return json.dumps(payload, ensure_ascii=False)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(_StructuredFormatter())
        logger.addHandler(handler)
        level = getattr(get_settings(), "log_level", "INFO").upper()
        logger.setLevel(getattr(logging, level, logging.INFO))
        logger.propagate = False
    return logger


def send_alert(
    subject: str,
    body: str,
    *,
    severity: str = "warning",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    results: dict[str, Any] = {"subject": subject, "severity": severity}

    email = getattr(settings, "alert_email", "") or ""
    if email:
        try:
            from app.services.email_service import send_alert as _email_alert

            results["email"] = _email_alert(email, subject=subject, body=body, severity=severity)
        except Exception as exc:
            results["email"] = {"status": "error", "error": str(exc)}

    webhook = getattr(settings, "alert_webhook_url", "") or ""
    if webhook:
        try:
            payload = {"subject": subject, "body": body, "severity": severity, "context": context or {}}
            with httpx.Client(timeout=15) as client:
                resp = client.post(webhook, json=payload)
                results["webhook"] = {
                    "status": "sent" if resp.status_code < 300 else "error",
                    "http": resp.status_code,
                }
        except Exception as exc:
            results["webhook"] = {"status": "error", "error": str(exc)}

    if not email and not webhook:
        results["note"] = "no alert channel configured"
        get_logger("observability").warning("alert sent without channels: %s", subject)

    get_logger("observability").info("alert dispatched: %s (%s)", subject, severity)
    return results


def health_snapshot(db: Any = None) -> dict[str, Any]:
    settings = get_settings()
    snapshot: dict[str, Any] = {
        "status": "healthy",
        "version": settings.version,
        "detector_mode": None,
        "db": "unknown",
        "email_transport": "smtp" if getattr(settings, "smtp_host", "") else "test",
        "alert_channels": {
            "email": bool(getattr(settings, "alert_email", "")),
            "webhook": bool(getattr(settings, "alert_webhook_url", "")),
        },
    }
    if db is not None:
        try:
            from sqlalchemy import text as _t

            db.execute(_t("SELECT 1"))
            snapshot["db"] = "ok"
        except Exception:
            snapshot["db"] = "error"
            snapshot["status"] = "degraded"
    try:
        from app.services.detector_factory import detector_mode

        snapshot["detector_mode"] = detector_mode()
    except Exception:
        snapshot["detector_mode"] = "unknown"
    return snapshot
