"""Three-tier configuration resolver (ADR-003): DB > env > code default.

`get(key)` is the only sanctioned read path at runtime.
`set(key, value, operator)` writes the DB tier and records an audit entry.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError, Err
from app.models.audit import AuditLog
from app.models.config import ConfigEntry

# key -> (default attribute name on Settings, type hint for JSON encoding)
_SCHEMA: dict[str, str] = {
    "default_conf_threshold": "default_conf_threshold",
    "default_iou_threshold": "default_iou_threshold",
    "default_imgsz": "default_imgsz",
    "default_val_ratio": "default_val_ratio",
    "default_holdout_ratio": "default_holdout_ratio",
    "enable_fallback_detector": "enable_fallback_detector",
    "default_weight_id": "default_weight_id",  # no Settings default
    "label_map": "label_map",  # no Settings default
    "llm_model": "llm_model",
    "embedding_model": "embedding_model",
}

# Sensitive keys must never be persisted to the DB (ADR-003 §实现约束)
_FORBIDDEN_KEYS = {"secret_key", "database_url", "access_token_expire_minutes"}


class ConfigService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    # ---------- read ----------
    def get(self, db: Session, key: str) -> Any:
        value, _ = self.get_with_source(db, key)
        return value

    def get_with_source(self, db: Session, key: str) -> tuple[Any, str]:
        self._validate_key(key)
        row = db.query(ConfigEntry).filter(ConfigEntry.key == key).first()
        if row is not None:
            return json.loads(row.value), "db"

        env_value = self._read_env(key)
        if env_value is not None:
            return env_value, "env"

        return self._read_default(key), "default"

    def snapshot(self, db: Session) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for key in _SCHEMA:
            value, source = self.get_with_source(db, key)
            out[key] = {"value": value, "source": source, "default": self._read_default(key)}
        return out

    # ---------- write ----------
    def set(self, db: Session, key: str, value: Any, operator: str | None = None, note: str | None = None) -> dict[str, Any]:
        self._validate_key(key)
        encoded = json.dumps(value, ensure_ascii=False)
        row = db.query(ConfigEntry).filter(ConfigEntry.key == key).first()
        old_value = row.value if row else None

        if row is None:
            row = ConfigEntry(key=key, value=encoded, updated_by=operator)
            db.add(row)
            action = "create"
        else:
            row.value = encoded
            row.updated_by = operator
            action = "update"

        db.add(
            AuditLog(
                entity="config",
                entity_key=key,
                old_value=old_value,
                new_value=encoded,
                operator=operator,
                action=action,
            )
        )
        if note:
            db.add(
                AuditLog(
                    entity="config",
                    entity_key=key,
                    old_value=None,
                    new_value=f"note: {note}",
                    operator=operator,
                    action="note",
                )
            )
        db.commit()
        return {"key": key, "value": value, "source": "db"}

    def reset(self, db: Session, key: str, operator: str | None = None) -> dict[str, Any]:
        """Remove the DB override so the value falls back to env / default."""
        self._validate_key(key)
        row = db.query(ConfigEntry).filter(ConfigEntry.key == key).first()
        if row is None:
            raise AppError(Err.NOT_FOUND, f"config key not found: {key}", 404)
        old_value = row.value
        db.delete(row)
        db.add(
            AuditLog(
                entity="config",
                entity_key=key,
                old_value=old_value,
                new_value=None,
                operator=operator,
                action="delete",
            )
        )
        db.commit()
        value, source = self.get_with_source(db, key)
        return {"key": key, "value": value, "source": source}

    # ---------- internal ----------
    def _validate_key(self, key: str) -> None:
        if key in _FORBIDDEN_KEYS:
            raise AppError(Err.FORBIDDEN, f"key not configurable at runtime: {key}", 403)
        if key not in _SCHEMA:
            raise AppError(Err.VALIDATION, f"unknown config key: {key}", 400)

    def _read_env(self, key: str) -> Any | None:
        # pydantic-settings already parsed env into `Settings`; only fall through
        # to it when the value actually differs from the code default.
        default = self._read_default(key)
        env_value = getattr(self._settings, key, None) if hasattr(self._settings, key) else None
        if env_value is None:
            return None
        return None if env_value == default else env_value

    def _read_default(self, key: str) -> Any:
        if key == "default_weight_id":
            return None
        if key == "label_map":
            return {}
        return getattr(self._settings, key, None)


_config_service: ConfigService | None = None


def get_config_service() -> ConfigService:
    global _config_service
    if _config_service is None:
        _config_service = ConfigService()
    return _config_service
