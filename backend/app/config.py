"""Application settings, loaded from environment variables / .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
MODELS_DIR = ROOT_DIR / "models"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    tavily_api_key: str = ""
    database_url: str = f"sqlite:///{ROOT_DIR / 'career_engine.db'}"
    secret_key: str = ""

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080"
    max_upload_mb: int = 5
    tavily_timeout_s: float = 20.0
    tavily_max_retries: int = 3
    tavily_cache_ttl_hours: int = 24
    tavily_concurrency: int = 4
    log_level: str = "INFO"

    @property
    def tavily_configured(self) -> bool:
        return bool(self.tavily_api_key.strip())

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
