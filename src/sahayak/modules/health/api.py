"""Cross-module public API for the health module."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from sahayak.core.db.session import UnitOfWork
from sahayak.modules.health.models import HealthEntry


class HealthAPI:
    """Public read API exposed to other modules (e.g. daily briefing)."""

    def __init__(
        self,
        session_factory: Any,
        clock: Any = None,
    ) -> None:
        self.session_factory = session_factory
        self.clock = clock or (lambda: datetime.now(UTC))

    async def get_daily_metrics(
        self,
        user_id: uuid.UUID,
        for_date: datetime | None = None,
    ) -> dict[str, Any]:
        """Aggregate water, meals, workouts, and sleep logged for a user today."""
        target = for_date or self.clock()
        day_start = datetime(target.year, target.month, target.day, 0, 0, 0, tzinfo=UTC)
        day_end = datetime(target.year, target.month, target.day, 23, 59, 59, 999999, tzinfo=UTC)

        async with UnitOfWork(self.session_factory) as uow:
            stmt = select(HealthEntry).where(
                HealthEntry.user_id == user_id,
                HealthEntry.is_deleted.is_(False),
                HealthEntry.occurred_at >= day_start,
                HealthEntry.occurred_at <= day_end,
            )
            res = await uow.session.execute(stmt)
            entries = list(res.scalars().all())

        water_ml = sum(e.data.get("amount_ml", 0) for e in entries if e.kind == "water")
        workouts = [e.data for e in entries if e.kind == "workout"]
        meals = [e.data for e in entries if e.kind == "meal"]
        sleep = [e.data for e in entries if e.kind == "sleep"]

        return {
            "date": target.date().isoformat(),
            "water_ml": water_ml,
            "workouts_count": len(workouts),
            "meals_count": len(meals),
            "sleep_logged": len(sleep) > 0,
        }
