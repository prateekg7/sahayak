"""Unit tests for deployment profiles and multi-addon resolution (T13.1, ADR 0016)."""

from __future__ import annotations

import pytest

from sahayak.core.config import Settings, get_settings
from sahayak.core.profiles import (
    BUNDLE_PROFILES,
    PROFILE_TOOL_BUDGETS,
    get_profile_modules,
    resolve_active_modules,
)


def test_get_profile_modules_known_profiles() -> None:
    """Every documented profile returns its canonical module tuple."""
    assert get_profile_modules("study") == ("academics",)
    assert get_profile_modules("life") == ("productivity", "finance", "health")
    assert get_profile_modules("work") == ("career", "business")
    assert get_profile_modules("home") == ("home", "language", "local_info")
    assert len(get_profile_modules("full")) == 9


def test_get_profile_modules_case_insensitive() -> None:
    """Profiles can be queried case-insensitively with leading/trailing spaces."""
    assert get_profile_modules("  STUDY  ") == ("academics",)
    assert get_profile_modules("Life") == ("productivity", "finance", "health")


def test_get_profile_modules_unknown_profile() -> None:
    """Querying an unknown profile raises a helpful ValueError."""
    with pytest.raises(ValueError, match="Unknown deployment profile 'gaming'"):
        get_profile_modules("gaming")


def test_resolve_active_modules_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit profile argument has highest precedence, then DEPLOYMENT_PROFILE env."""
    # 1. Default without env
    monkeypatch.delenv("DEPLOYMENT_PROFILE", raising=False)
    monkeypatch.delenv("ENABLED_MODULES", raising=False)
    assert resolve_active_modules() == BUNDLE_PROFILES["full"]

    # 2. ENABLED_MODULES env
    monkeypatch.setenv("ENABLED_MODULES", "academics, health")
    assert resolve_active_modules() == ("academics", "health")

    # 3. DEPLOYMENT_PROFILE env overrides ENABLED_MODULES
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "study")
    assert resolve_active_modules() == ("academics",)

    # 4. Explicit profile argument overrides all env
    assert resolve_active_modules(profile_name="work") == ("career", "business")

    # 5. Explicit enabled_modules argument when profile_name is None and env is cleared
    monkeypatch.delenv("DEPLOYMENT_PROFILE", raising=False)
    assert resolve_active_modules(enabled_modules=("finance",)) == ("finance",)


def test_settings_resolves_deployment_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings validator switches enabled_modules when deployment_profile is set."""
    # Direct instantiation with profile
    settings = Settings(deployment_profile="life", _env_file=None)  # type: ignore[call-arg]
    assert settings.deployment_profile == "life"
    assert settings.enabled_modules == ("productivity", "finance", "health")

    # Via environment variable
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "work")
    get_settings.cache_clear()
    env_settings = get_settings()
    assert env_settings.deployment_profile == "work"
    assert env_settings.enabled_modules == ("career", "business")
    get_settings.cache_clear()


def test_profile_tool_budgets_within_alexa_limits() -> None:
    """Each individual add-on profile must stay strictly within its configured tool budget."""
    for profile, max_budget in PROFILE_TOOL_BUDGETS.items():
        assert max_budget > 0
        if profile != "full":
            # Individual add-on bundles must be manageable for Alexa+ (<= 12 tools)
            assert max_budget <= 12, f"Profile {profile} budget {max_budget} exceeds Alexa limit 12"
