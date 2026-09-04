"""Application configuration.

All settings can be overridden through environment variables (or a .env file
placed next to the backend package).
"""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AI PMO"
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./ai_pmo.db")

    # CORS origins for the Next.js frontend.
    cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")

    # LLM (optional). When no key is configured the deterministic reasoning
    # engine is used instead, so the product works fully offline.
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY") or None
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    llm_enabled: bool = os.getenv("LLM_ENABLED", "auto") != "off"

    # Temporary storage for uploaded spreadsheets awaiting import confirmation.
    upload_dir: str = os.getenv("UPLOAD_DIR", "./_uploads")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def llm_available(self) -> bool:
        return bool(self.llm_enabled and self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
