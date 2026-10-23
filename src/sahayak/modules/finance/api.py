"""Public API published by the finance module for cross-module interactions (T6.1)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from sahayak.core.db.session import SessionFactory, UnitOfWork
from sahayak.modules.finance.adapters.expenses import SQLAlchemyExpenseRepository


@runtime_checkable
class FinanceModuleAPI(Protocol):
    """Protocol for cross-module callers to interact with Finance capabilities."""

    async def get_total_spending(
        self,
        user_id: str | uuid.UUID,
        currency: str = "INR",
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> int:
        """Return total active spending in integer minor units for the specified period."""
        ...


class FinanceAPI:
    """Implementation of FinanceModuleAPI backed by SQLAlchemy and domain services."""

    def __init__(
        self,
        session_factory: SessionFactory,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def _normalize_uuid(self, user_id: str | uuid.UUID) -> uuid.UUID:
        if isinstance(user_id, uuid.UUID):
            return user_id
        return uuid.UUID(str(user_id))

    async def get_total_spending(
        self,
        user_id: str | uuid.UUID,
        currency: str = "INR",
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> int:
        """Return total active spending in integer minor units for the specified period."""
        uid = self._normalize_uuid(user_id)
        async with UnitOfWork(self._session_factory) as uow:
            repo = SQLAlchemyExpenseRepository(uow.session)
            return await repo.get_total_spending(
                user_id=uid,
                currency=currency,
                since=since,
                until=until,
            )
