"""Validated application configuration loaded from environment variables."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Annotated

from pydantic import AnyUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class AppEnvironment(StrEnum):
    """Supported deployment environments."""

    LOCAL = "local"
    STAGING = "staging"
    PROD = "prod"


NonEmptyString = Annotated[str, Field(min_length=1)]
PositiveInt = Annotated[int, Field(gt=0)]


class Settings(BaseSettings):
    """Load and validate all Sahayak configuration from environment variables.

    Raises:
        pydantic.ValidationError: If an environment value is invalid or a required
            production setting is missing.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: AppEnvironment = AppEnvironment.LOCAL
    app_name: NonEmptyString = "Sahayak"
    public_base_url: AnyUrl = AnyUrl("http://localhost:8000")
    enabled_modules: Annotated[tuple[NonEmptyString, ...], NoDecode] = ("academics",)

    database_url: AnyUrl = AnyUrl("postgresql+asyncpg://sahayak:sahayak@localhost:5432/sahayak")
    redis_url: AnyUrl = AnyUrl("redis://localhost:6379/0")
    allowed_origins: Annotated[tuple[AnyUrl, ...], NoDecode] = ()

    max_tools: PositiveInt = 15
    max_tools_per_module: PositiveInt = 4
    spoken_summary_max_chars: PositiveInt = 300
    max_response_bytes: PositiveInt = 8192
    request_timeout_seconds: Annotated[float, Field(gt=0, le=0.5)] = 0.45
    rate_limit_per_minute: PositiveInt = 60
    rate_limit_generation_per_minute: PositiveInt = 10

    oidc_issuer: AnyUrl | None = None
    oidc_audience: NonEmptyString | None = None
    oidc_jwks_url: AnyUrl | None = None

    llm_primary_provider: NonEmptyString = "gemini"
    llm_fallback_provider: NonEmptyString = "groq"
    llm_primary_model: NonEmptyString | None = None
    llm_fallback_model: NonEmptyString | None = None
    gemini_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    llm_daily_budget_requests: PositiveInt = 1000

    quiz_ttl_minutes: PositiveInt = 120
    otel_exporter_otlp_endpoint: AnyUrl | None = None
    sentry_dsn: SecretStr | None = None

    @field_validator("enabled_modules", mode="before")
    @classmethod
    def parse_enabled_modules(cls, value: object) -> tuple[str, ...] | object:
        """Convert the comma-separated environment form into a non-empty tuple."""
        if not isinstance(value, str):
            return value
        modules = tuple(module.strip() for module in value.split(",") if module.strip())
        if not modules:
            msg = "ENABLED_MODULES must contain at least one module"
            raise ValueError(msg)
        return modules

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: object) -> tuple[str, ...] | object:
        """Convert optional comma-separated origins into a tuple."""
        if not isinstance(value, str):
            return value
        return tuple(origin.strip() for origin in value.split(",") if origin.strip())

    @field_validator("database_url")
    @classmethod
    def validate_database_scheme(cls, value: AnyUrl) -> AnyUrl:
        """Require the async PostgreSQL URL used by the application."""
        if value.scheme != "postgresql+asyncpg":
            msg = "DATABASE_URL must use the postgresql+asyncpg scheme"
            raise ValueError(msg)
        return value

    @field_validator("redis_url")
    @classmethod
    def validate_redis_scheme(cls, value: AnyUrl) -> AnyUrl:
        """Require a Redis URL for the shared cache and rate limiter."""
        if value.scheme not in {"redis", "rediss"}:
            msg = "REDIS_URL must use the redis or rediss scheme"
            raise ValueError(msg)
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide immutable settings instance.

    Raises:
        pydantic.ValidationError: If configuration cannot be validated.
    """
    return Settings()
