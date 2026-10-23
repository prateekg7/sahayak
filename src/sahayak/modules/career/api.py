"""Published cross-module API for career module (T8.2)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sahayak.core.db.session import UnitOfWork
from sahayak.modules.career.adapters.applications import SQLAlchemyApplicationRepository


class CareerAPI:
    """Public contract through which other modules interact with Career."""

    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    async def get_due_followups(
        self,
        user_id: uuid.UUID,
        window_hours: int = 24,
    ) -> list[dict[str, Any]]:
        """Retrieve applications with upcoming follow-ups due within window_hours."""
        now = datetime.now(UTC)
        cutoff = now + timedelta(hours=window_hours)
        async with UnitOfWork(self._session_factory) as uow:
            repo = SQLAlchemyApplicationRepository(uow.session)
            apps = await repo.list_due_followups(user_id=user_id, before_time=cutoff, limit=5)
            return [
                {
                    "id": str(a.id),
                    "company": a.company,
                    "role": a.role,
                    "status": a.status,
                    "follow_up_at": a.follow_up_at.isoformat() if a.follow_up_at else None,
                }
                for a in apps
            ]
