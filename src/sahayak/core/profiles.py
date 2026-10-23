"""Deployment profiles and multi-addon bundle resolution (T13.1, ADR 0016)."""

from __future__ import annotations

import os

BUNDLE_PROFILES: dict[str, tuple[str, ...]] = {
    "study": ("academics",),
    "life": ("productivity", "finance", "health"),
    "work": ("career", "business"),
    "home": ("home", "language", "local_info"),
    "full": (
        "academics",
        "productivity",
        "finance",
        "health",
        "career",
        "home",
        "business",
        "language",
        "local_info",
    ),
}

PROFILE_TOOL_BUDGETS: dict[str, int] = {
    "study": 6,
    "life": 12,
    "work": 8,
    "home": 10,
    "full": 35,
}


def get_profile_modules(profile: str) -> tuple[str, ...]:
    """Retrieve enabled modules for a specific deployment profile."""
    clean = profile.strip().lower()
    if clean not in BUNDLE_PROFILES:
        valid = ", ".join(sorted(BUNDLE_PROFILES.keys()))
        raise ValueError(f"Unknown deployment profile '{profile}'. Valid profiles: {valid}")
    return BUNDLE_PROFILES[clean]


def resolve_active_modules(
    profile_name: str | None = None,
    enabled_modules: tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    """Resolve active modules considering profile parameter, env vars, or defaults."""
    # 1. Explicit profile parameter or DEPLOYMENT_PROFILE env
    active_profile = profile_name or os.environ.get("DEPLOYMENT_PROFILE")
    if active_profile:
        return get_profile_modules(active_profile)

    # 2. Explicit modules parameter or ENABLED_MODULES env
    if enabled_modules is not None:
        return enabled_modules

    env_modules = os.environ.get("ENABLED_MODULES")
    if env_modules:
        parsed = tuple(m.strip() for m in env_modules.split(",") if m.strip())
        if parsed:
            return parsed

    # 3. Default to full profile
    return BUNDLE_PROFILES["full"]
