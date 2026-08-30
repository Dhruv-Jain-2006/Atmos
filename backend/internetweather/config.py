"""Application configuration.

Read once at import time from the environment / .env. The API must be able to
BOOT without a database so the scaffold is verifiable and so a suspended Neon
compute or exhausted quota degrades rather than crashes.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: str = "development"
    log_level: str = "INFO"

    # Pooled URL for the read API; direct URL for migrations and workers.
    database_url: str | None = None
    database_url_direct: str | None = None

    github_token: str | None = None

    llm_provider: str = "none"
    gemini_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"

    cors_origins: str = "http://localhost:3000"

    @property
    def database_configured(self) -> bool:
        return bool(self.database_url or self.database_url_direct)

    @property
    def api_database_url(self) -> str | None:
        """URL the read API should use — prefer the pooled endpoint."""
        return self.database_url or self.database_url_direct

    @property
    def worker_database_url(self) -> str | None:
        """URL workers and Alembic should use — prefer the direct endpoint.

        DDL and long-running transactions do not belong on a PgBouncer
        connection in transaction-pooling mode.
        """
        return self.database_url_direct or self.database_url

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
