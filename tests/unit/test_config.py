"""Tests for validated application settings."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from sahayak.core.config import AppEnvironment, Settings, get_settings


def test_settings_defaults_are_safe() -> None:
    """Use local defaults with an explicitly configured module."""
    settings = Settings(_env_file=None)  # type: ignore[call-arg]  # Pydantic Settings runtime API.

    assert settings.app_env is AppEnvironment.LOCAL
    assert settings.enabled_modules == ("academics",)
    assert str(settings.database_url).startswith("postgresql+asyncpg://")
    assert settings.request_timeout_seconds == 0.45


def test_settings_read_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Parse valid environment values without retaining stale cached settings."""
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("ENABLED_MODULES", "academics, productivity")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://alexa.example, https://admin.example")
    monkeypatch.setenv("GEMINI_API_KEY", "not-a-real-key")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.app_env is AppEnvironment.STAGING
    assert settings.enabled_modules == ("academics", "productivity")
    assert tuple(str(origin) for origin in settings.allowed_origins) == (
        "https://alexa.example/",
        "https://admin.example/",
    )
    assert settings.gemini_api_key is not None
    assert settings.gemini_api_key.get_secret_value() == "not-a-real-key"
    get_settings.cache_clear()


@pytest.mark.parametrize(
    ("environment", "expected_message"),
    [
        ({"APP_ENV": "development"}, "app_env"),
        ({"ENABLED_MODULES": " , "}, "ENABLED_MODULES must contain at least one module"),
        ({"DATABASE_URL": "postgresql://localhost/sahayak"}, r"postgresql\+asyncpg"),
        ({"REDIS_URL": "http://localhost:6379"}, "redis or rediss"),
        ({"REQUEST_TIMEOUT_SECONDS": "0.6"}, "less than or equal to 0.5"),
    ],
)
def test_settings_reject_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
    environment: dict[str, str],
    expected_message: str,
) -> None:
    """Fail fast when a required configuration invariant is violated."""
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError, match=expected_message):
        Settings(_env_file=None)  # type: ignore[call-arg]  # Pydantic Settings runtime API.


def test_secrets_are_masked_in_settings_repr() -> None:
    """Never reveal secret values through model representations."""
    settings = Settings(  # type: ignore[call-arg]  # Pydantic Settings runtime API.
        _env_file=None,
        gemini_api_key=SecretStr("not-a-real-key"),
    )

    assert "not-a-real-key" not in repr(settings)
