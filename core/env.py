"""
Application settings loaded from environment variables and .env file.

All hardcoded connection strings, ports, API keys, and feature flags live here.
Consumers call get_settings() to retrieve the singleton instance.

Usage:
    from core.env import get_settings
    settings = get_settings()
    uri = settings.mongodb_uri
"""

from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # ── Database ──────────────────────────────────────────────
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "adversarial_testing"

    # ── Server ────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:3001"]

    # ── LLM Providers ─────────────────────────────────────────
    openai_api_key: str = ""
    gemini_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # ── Logging / Debug ───────────────────────────────────────
    debug_enabled: bool = False
    log_level: str = "warning"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # Allow extra env vars without error
        extra = "ignore"


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the application settings singleton, loading .env on first call."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
