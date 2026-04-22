"""Central configuration for ADP.

All secrets come from environment variables — never hardcoded (ADR-002).
Use get_settings() everywhere; the result is cached with @lru_cache.

Model names follow LiteLLM conventions:
  - Claude  : "claude-sonnet-4-6"   (Anthropic SDK)
  - Gemini  : "gemini/gemini-2.0-flash"  (Google SDK via LiteLLM)
  - Codex   : "openai/gpt-4o"       (OpenAI SDK via LiteLLM)
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Dict, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------
    # Database (ADR-001)
    # ------------------------------------------------------------------
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/adp",
        description="asyncpg URL for runtime. Alembic auto-converts to psycopg2.",
    )
    sql_echo: bool = Field(default=False)

    # ------------------------------------------------------------------
    # LLM API keys (ADR-002 — never hardcoded)
    # ------------------------------------------------------------------
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    google_api_key: str = Field(default="", alias="GOOGLE_API_KEY")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    litellm_master_key: str = Field(default="", alias="LITELLM_MASTER_KEY")

    # ------------------------------------------------------------------
    # Model identifiers (LiteLLM naming convention)
    # ------------------------------------------------------------------
    claude_model: str = Field(
        default="claude-sonnet-4-6",
        description="Primary Claude model. Roles: backend, architecture, APIs.",
    )
    gemini_model: str = Field(
        default="gemini/gemini-2.5-flash",
        description="Primary Gemini model. Roles: UI/UX, frontend, components.",
    )
    codex_model: str = Field(
        default="openai/gpt-4o",
        description="Primary Codex/OpenAI model. Roles: security review, tests.",
    )

    # ------------------------------------------------------------------
    # Fallback chains per assigned_model (ADR-002: max 2 fallbacks)
    # Index 0 = primary, index 1 = first fallback, index 2 = last fallback
    # ------------------------------------------------------------------
    claude_fallback_chain: List[str] = Field(
        default=["claude-sonnet-4-6", "openai/gpt-4o", "gemini/gemini-2.5-flash"]
    )
    gemini_fallback_chain: List[str] = Field(
        default=["gemini/gemini-2.5-flash", "claude-sonnet-4-6", "openai/gpt-4o"]
    )
    codex_fallback_chain: List[str] = Field(
        default=["openai/gpt-4o", "claude-sonnet-4-6", "gemini/gemini-2.5-flash"]
    )

    # ------------------------------------------------------------------
    # Timeouts & retry policy
    # ------------------------------------------------------------------
    request_timeout_s: int = Field(
        default=60,
        description="Per-request timeout in seconds before fallback triggers.",
    )
    max_fallback_attempts: int = Field(
        default=3,
        description="Total attempts including primary. Must equal len(fallback_chain).",
    )

    # ------------------------------------------------------------------
    # Rate limits (requests per minute) — informational for monitoring
    # ------------------------------------------------------------------
    rpm_claude: int = Field(default=50)
    rpm_gemini: int = Field(default=60)
    rpm_codex: int = Field(default=60)

    # ------------------------------------------------------------------
    # JWT Authentication (PRE-4.0)
    # ------------------------------------------------------------------
    jwt_secret: str = Field(
        default="",
        alias="JWT_SECRET",
        description="HS256 signing secret. Must be provided via environment variable.",
    )
    jwt_algorithm: str = Field(default="HS256")
    jwt_expiration_minutes: int = Field(default=15)

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    app_env: str = Field(default="development")
    log_level: str = Field(default="INFO")

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------

    def get_fallback_chain(self, model_key: str) -> List[str]:
        """Return ordered fallback chain for a given AgentModel value."""
        chains: Dict[str, List[str]] = {
            "claude": self.claude_fallback_chain,
            "gemini": self.gemini_fallback_chain,
            "codex": self.codex_fallback_chain,
        }
        return chains.get(model_key, self.claude_fallback_chain)

    def get_rpm_limit(self, model_key: str) -> int:
        limits: Dict[str, int] = {
            "claude": self.rpm_claude,
            "gemini": self.rpm_gemini,
            "codex": self.rpm_codex,
        }
        return limits.get(model_key, 60)

    @field_validator("app_env")
    @classmethod
    def validate_env(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"app_env must be one of {allowed}")
        return v

    @field_validator("jwt_secret")
    @classmethod
    def normalize_jwt_secret(cls, value: str) -> str:
        return value.strip()

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton. Call get_settings.cache_clear() in tests."""
    return Settings()
