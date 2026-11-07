"""Application configuration — three-tier priority: DB > env > code default.

See ADR-003. `Settings` reads env/`.env`; `ConfigService` (services/config_service.py)
layers the DB on top and is the only sanctioned read path at runtime.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "VisionFlywheel"
    version: str = "0.1.0"
    debug: bool = False

    # Security — must come from env in production
    secret_key: str = Field(default="dev-secret-change-me-in-env")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    bcrypt_rounds: int = 12

    # Storage
    database_url: str = "sqlite:///./runtime_data/app.db"
    upload_dir: str = "runtime_data/uploads"
    result_dir: str = "runtime_data/results"
    dataset_dir: str = "runtime_data/datasets"
    weights_dir: str = "backend/weights"

    # CORS
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])

    # Business defaults (overridable via DB / env, see ADR-003)
    default_conf_threshold: float = 0.5
    default_iou_threshold: float = 0.45
    default_imgsz: int = 640
    default_val_ratio: float = 0.2
    default_holdout_ratio: float = 0.1
    enable_fallback_detector: bool = True

    # LLM (used from M5)
    llm_model: str = "Qwen/Qwen2.5-0.5B-Instruct"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache
def get_settings() -> Settings:
    return Settings()
