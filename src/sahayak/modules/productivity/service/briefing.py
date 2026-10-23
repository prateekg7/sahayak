"""Unified daily briefing service coordinating productivity and academics APIs (T5.5)."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sahayak.core.db.session import UnitOfWork
from sahayak.modules.productivity.adapters.focus import SQLAlchemyFocusRepository
from sahayak.modules.productivity.adapters.habits import SQLAlchemyHabitRepository
from sahayak.modules.productivity.adapters.tasks import SQLAlchemyTaskRepository
from sahayak.modules.productivity.domain.briefing import (
    BriefingItems,
    format_daily_briefing_spoken,
)
from sahayak.modules.productivity.ports import AcademicsAPIPort
from sahayak.modules.productivity.schemas import DailyBriefingData

logger = logging.getLogger(__name__)


class BriefingService:
    """Service orchestrating cross-module daily briefings with graceful degradation."""

    def __init__(
        self,
        session_factory: Any,
        academics_api_getter: Callable[[], AcademicsAPIPort | None] | None = None,
        business_api_getter: Callable[[], Any] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.academics_api_getter = academics_api_getter
        self.business_api_getter = business_api_getter
        self.clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        dt = self.clock()
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)

    def _resolve_zone(self, tz_str: str) -> ZoneInfo:
        try:
            return ZoneInfo(tz_str)
        except (ZoneInfoNotFoundError, ValueError):
            return ZoneInfo("UTC")

    async def get_daily_briefing(
        self,
        user_id: uuid.UUID,
        timezone_str: str = "UTC",
    ) -> tuple[str, DailyBriefingData, list[str]]:
        """Assemble an ordered, concise daily briefing across enabled modules."""
        now = self._now()
        user_tz = self._resolve_zone(timezone_str)
        local_now = now.astimezone(user_tz)
        local_today = local_now.date()

        start_of_day = datetime.combine(local_today, time.min, tzinfo=user_tz).astimezone(UTC)
        end_of_day = datetime.combine(local_today, time.max, tzinfo=user_tz).astimezone(UTC)

        async with UnitOfWork(self.session_factory) as uow:
            task_repo = SQLAlchemyTaskRepository(uow.session)
            habit_repo = SQLAlchemyHabitRepository(uow.session)
            focus_repo = SQLAlchemyFocusRepository(uow.session)

            # 1. Tasks due today
            due_tasks = await task_repo.get_due_today_tasks(user_id, start_of_day, end_of_day)
            due_task_titles = [t.title for t in due_tasks]

            # 2. Habits pending today
            habits = await habit_repo.list_habits(user_id, include_archived=False)
            pending_habits = [h.name for h in habits if h.last_logged_date != local_today]

            # 3. Focus sessions completed today
            _, _, today_focus = await focus_repo.get_session_stats(user_id, start_of_day)

        # 4. Optional Academics API
        academics_enabled = False
        flashcards_due = 0
        study_tasks: list[str] = []
        study_streak = 0

        academics_api = self.academics_api_getter() if self.academics_api_getter else None
        if academics_api is not None:
            academics_enabled = True
            try:
                flashcards_due = await academics_api.get_due_flashcard_count(user_id, before=now)
                study_tasks = await academics_api.get_today_study_tasks(
                    user_id, timezone_str=timezone_str
                )
                study_streak = await academics_api.get_streak(user_id, timezone_str=timezone_str)
            except Exception:
                # Graceful degradation if academics API query fails
                academics_enabled = False

        # 5. Optional Business API for low stock alerts (T10.3)
        low_stock_items: list[str] = []
        biz_api = self.business_api_getter() if self.business_api_getter else None
        if biz_api is not None:
            try:
                low_prods = await biz_api.get_low_stock_summary(user_id=user_id)
                low_stock_items = [p["name"] for p in low_prods]
            except Exception as exc:
                logger.debug("Failed to retrieve low stock summary for user %s: %s", user_id, exc)

        items = BriefingItems(
            tasks_due=due_task_titles,
            habits_pending=pending_habits,
            academics_enabled=academics_enabled,
            flashcards_due_count=flashcards_due,
            study_tasks=study_tasks,
            study_streak=study_streak,
            focus_today_completed=today_focus,
        )

        spoken = format_daily_briefing_spoken(items)
        if low_stock_items:
            stock_phrase = f" Low stock alert: {', '.join(low_stock_items[:2])}."
            if len(spoken) + len(stock_phrase) <= 300:
                spoken = spoken + stock_phrase

        data = DailyBriefingData(
            tasks_due_count=len(due_task_titles),
            tasks_due=due_task_titles,
            habits_pending_count=len(pending_habits),
            habits_pending=pending_habits,
            academics_enabled=academics_enabled,
            flashcards_due_count=flashcards_due if academics_enabled else None,
            study_tasks=study_tasks if academics_enabled else [],
            study_streak=study_streak if academics_enabled else None,
            focus_today_completed=today_focus,
            low_stock_items=low_stock_items,
        )

        next_actions = ["what are my tasks", "start a focus session"]
        if academics_enabled and flashcards_due > 0:
            next_actions.append("review flashcards")
        if low_stock_items:
            next_actions.append("sales_summary(action='low_stock')")
        return spoken, data, next_actions
