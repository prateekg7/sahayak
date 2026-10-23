"""Feature flags and per-user module toggles store (T13.3)."""

from __future__ import annotations

import functools
import hashlib
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Uuid, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sahayak.core.auth.principal import get_current_principal
from sahayak.core.db.base import Base
from sahayak.core.db.session import SessionFactory, UnitOfWork
from sahayak.core.envelope import fail
from sahayak.core.errors import SahayakError

logger = logging.getLogger(__name__)


class FeatureFlagRecord(Base):
    """Database model storing feature flag definitions, rollout percentage, and user overrides."""

    __tablename__ = "feature_flags"
    __table_args__ = {"schema": "core"}

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    rollout_percentage: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    user_overrides: Mapped[dict[str, bool]] = mapped_column(JSONB, default=dict, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UserPreferenceRecord(Base):
    """Database model storing per-user disabled modules and preferences."""

    __tablename__ = "user_preferences"
    __table_args__ = {"schema": "core"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("core.users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    disabled_modules: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class FeatureFlagStore:
    """Manages feature flag state with local overrides and database persistence."""

    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        self.session_factory = session_factory
        self._memory_flags: dict[str, dict[str, Any]] = {}

    def set_in_memory_flag(
        self,
        name: str,
        enabled: bool,
        rollout_percentage: int = 100,
        user_overrides: dict[str, bool] | None = None,
        description: str | None = None,
    ) -> None:
        """Store or override a feature flag in memory (useful for testing or config fallback)."""
        self._memory_flags[name] = {
            "name": name,
            "enabled": enabled,
            "rollout_percentage": max(0, min(100, rollout_percentage)),
            "user_overrides": dict(user_overrides or {}),
            "description": description,
        }

    async def get_flag_state(self, name: str) -> dict[str, Any] | None:
        """Fetch flag definition from in-memory cache or database."""
        if name in self._memory_flags:
            return self._memory_flags[name]

        if self.session_factory is not None:
            async with UnitOfWork(self.session_factory) as uow:
                stmt = select(FeatureFlagRecord).where(FeatureFlagRecord.name == name)
                res = await uow.session.execute(stmt)
                record = res.scalars().first()
                if record is not None:
                    return {
                        "name": record.name,
                        "enabled": record.enabled,
                        "rollout_percentage": record.rollout_percentage,
                        "user_overrides": dict(record.user_overrides),
                        "description": record.description,
                    }
        return None

    async def is_enabled(
        self,
        name: str,
        user_id: str | uuid.UUID | None = None,
    ) -> bool:
        """Evaluate if a feature flag is enabled for the specified user."""
        flag = await self.get_flag_state(name)
        if flag is None:
            # Undefined flags default to enabled
            return True

        uid_str = str(user_id) if user_id is not None else None

        # 1. Per-user override takes highest priority
        if uid_str is not None and uid_str in flag["user_overrides"]:
            return bool(flag["user_overrides"][uid_str])

        # 2. Master kill switch
        if not flag["enabled"]:
            return False

        # 3. Percentage rollout
        pct = int(flag.get("rollout_percentage", 100) or 0)
        if pct >= 100:
            return True
        if pct <= 0:
            return False

        if uid_str is None:
            return False

        # Deterministic hash of user_id + flag_name
        digest = hashlib.sha256(f"{name}:{uid_str}".encode()).hexdigest()
        bucket = int(digest[:8], 16) % 100
        return bool(bucket < pct)

    async def persist_flag(
        self,
        name: str,
        enabled: bool,
        rollout_percentage: int = 100,
        user_overrides: dict[str, bool] | None = None,
        description: str | None = None,
    ) -> None:
        """Persist a feature flag to database and update memory cache."""
        clean_name = name.strip()
        overrides = dict(user_overrides or {})
        clean_pct = max(0, min(100, rollout_percentage))

        self.set_in_memory_flag(
            name=clean_name,
            enabled=enabled,
            rollout_percentage=clean_pct,
            user_overrides=overrides,
            description=description,
        )

        if self.session_factory is not None:
            async with UnitOfWork(self.session_factory) as uow:
                stmt = select(FeatureFlagRecord).where(FeatureFlagRecord.name == clean_name)
                res = await uow.session.execute(stmt)
                record = res.scalars().first()
                if record is None:
                    record = FeatureFlagRecord(
                        name=clean_name,
                        enabled=enabled,
                        rollout_percentage=clean_pct,
                        user_overrides=overrides,
                        description=description,
                    )
                    uow.session.add(record)
                else:
                    record.enabled = enabled
                    record.rollout_percentage = clean_pct
                    record.user_overrides = overrides
                    if description is not None:
                        record.description = description
                    record.updated_at = datetime.now(UTC)


_global_flag_store: FeatureFlagStore = FeatureFlagStore()


def get_feature_flag_store() -> FeatureFlagStore:
    """Return the singleton FeatureFlagStore instance."""
    return _global_flag_store


def set_feature_flag_store(store: FeatureFlagStore) -> None:
    """Set the singleton FeatureFlagStore instance."""
    global _global_flag_store
    _global_flag_store = store


class FeatureDisabledError(SahayakError):
    """Raised when an operation is gated by a disabled feature flag."""

    code: str = "feature_disabled"

    def __init__(
        self,
        spoken: str = "This feature is temporarily unavailable. Please try again later.",
        *,
        detail: str | None = None,
    ) -> None:
        super().__init__(spoken, detail=detail)


def check_feature_flag(flag_name: str) -> Callable[..., Any]:
    """Decorator guarding a tool or service function with a feature flag."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            store = get_feature_flag_store()
            principal = get_current_principal()
            user_id = principal.user_id if principal else None

            if not await store.is_enabled(flag_name, user_id=user_id):
                logger.info("feature_flag_blocked flag=%s user_id=%s", flag_name, user_id)
                return fail(
                    FeatureDisabledError(),
                    module="core",
                    version="0.1.0",
                )
            return await fn(*args, **kwargs)

        return wrapper

    return decorator


class UserPreferenceService:
    """Manages per-user module toggles and personal preferences."""

    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        self.session_factory = session_factory
        self._memory_prefs: dict[uuid.UUID, set[str]] = {}

    async def get_disabled_modules(self, user_id: uuid.UUID) -> set[str]:
        """Return the set of modules disabled by the user."""
        if user_id in self._memory_prefs:
            return set(self._memory_prefs[user_id])

        if self.session_factory is not None:
            async with UnitOfWork(self.session_factory) as uow:
                stmt = select(UserPreferenceRecord).where(UserPreferenceRecord.user_id == user_id)
                res = await uow.session.execute(stmt)
                record = res.scalars().first()
                if record is not None:
                    disabled = set(record.disabled_modules)
                    self._memory_prefs[user_id] = disabled
                    return disabled
        return set()

    async def is_module_enabled(self, user_id: uuid.UUID, module_name: str) -> bool:
        """Check whether a specific module is active for the user."""
        disabled = await self.get_disabled_modules(user_id)
        return module_name.strip().lower() not in disabled

    async def set_module_enabled(
        self,
        user_id: uuid.UUID,
        module_name: str,
        enabled: bool,
    ) -> None:
        """Enable or disable a specific module for the given user."""
        clean = module_name.strip().lower()
        disabled = await self.get_disabled_modules(user_id)
        if enabled:
            disabled.discard(clean)
        else:
            disabled.add(clean)

        self._memory_prefs[user_id] = set(disabled)

        if self.session_factory is not None:
            async with UnitOfWork(self.session_factory) as uow:
                stmt = select(UserPreferenceRecord).where(UserPreferenceRecord.user_id == user_id)
                res = await uow.session.execute(stmt)
                record = res.scalars().first()
                if record is None:
                    record = UserPreferenceRecord(
                        user_id=user_id,
                        disabled_modules=list(disabled),
                    )
                    uow.session.add(record)
                else:
                    record.disabled_modules = list(disabled)
                    record.updated_at = datetime.now(UTC)


_global_user_pref_service: UserPreferenceService = UserPreferenceService()


def get_user_preference_service() -> UserPreferenceService:
    """Return the singleton UserPreferenceService."""
    return _global_user_pref_service


def set_user_preference_service(service: UserPreferenceService) -> None:
    """Set the singleton UserPreferenceService."""
    global _global_user_pref_service
    _global_user_pref_service = service
