"""Service for assembling cross-module weekly reviews (T13.2)."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sahayak.modules.productivity.domain.weekly_review import (
    WeeklyFinanceStats,
    WeeklyHabitStats,
    WeeklyHealthStats,
    WeeklyReviewSummary,
    WeeklyStudyStats,
    format_weekly_review_spoken,
)

logger = logging.getLogger(__name__)


class WeeklyReviewService:
    """Orchestrates cross-module weekly summary aggregation across published APIs."""

    def __init__(
        self,
        session_factory: Any,
        module_api_getter: Callable[[str], Any | None] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.module_api_getter = module_api_getter
        self.clock = clock or (lambda: datetime.now(UTC))

    def _get_api(self, module_name: str) -> Any | None:
        if self.module_api_getter is None:
            return None
        try:
            return self.module_api_getter(module_name)
        except Exception as exc:
            logger.debug("Failed to get API for module %s: %s", module_name, exc)
            return None

    async def get_weekly_review(
        self,
        user_id: uuid.UUID,
        timezone_str: str = "UTC",
    ) -> tuple[str, WeeklyReviewSummary, list[str]]:
        """Query enabled module APIs and generate an adaptive weekly review."""
        now = self.clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        seven_days_ago = now - timedelta(days=7)

        enabled_modules: list[str] = []
        highlights: list[str] = []

        study_stats: WeeklyStudyStats | None = None
        habit_stats: WeeklyHabitStats | None = None
        finance_stats: WeeklyFinanceStats | None = None
        health_stats: WeeklyHealthStats | None = None

        # 1. Academics
        academics_api = self._get_api("academics")
        if academics_api is not None:
            enabled_modules.append("academics")
            try:
                summary = await academics_api.get_weekly_summary(user_id, timezone_str=timezone_str)
                streak_info = await academics_api.get_streak_info(
                    user_id, timezone_str=timezone_str
                )
                study_stats = WeeklyStudyStats(
                    quizzes_completed=summary.get("quizzes_completed", 0),
                    questions_answered=summary.get("questions_answered", 0),
                    accuracy_pct=summary.get("accuracy_pct", 0.0),
                    streak_days=streak_info.current_streak,
                    is_streak_record=(
                        streak_info.current_streak >= streak_info.longest_streak
                        and streak_info.current_streak > 1
                    ),
                )
                if study_stats.is_streak_record:
                    highlights.append(
                        f"Longest study streak ever at {study_stats.streak_days} days"
                    )
            except Exception as exc:
                logger.warning("Error fetching academics weekly stats: %s", exc)

        # 2. Productivity Habits
        productivity_api = self._get_api("productivity")
        if productivity_api is not None:
            enabled_modules.append("productivity")
            try:
                h_stats = await productivity_api.get_weekly_habit_stats(
                    user_id, timezone_str=timezone_str
                )
                habit_stats = WeeklyHabitStats(
                    active_count=h_stats.get("active_count", 0),
                    completions_count=h_stats.get("completions_count", 0),
                    top_habit=h_stats.get("top_habit"),
                )
                if habit_stats.top_habit and not highlights:
                    highlights.append(f"Top habit was {habit_stats.top_habit}")
            except Exception as exc:
                logger.warning("Error fetching habits weekly stats: %s", exc)

        # 3. Finance
        finance_api = self._get_api("finance")
        if finance_api is not None:
            enabled_modules.append("finance")
            try:
                spending_minor = await finance_api.get_total_spending(
                    user_id=user_id,
                    currency="INR",
                    since=seven_days_ago,
                    until=now,
                )
                finance_stats = WeeklyFinanceStats(
                    total_spent_minor=spending_minor,
                    currency="INR",
                )
            except Exception as exc:
                logger.warning("Error fetching finance weekly stats: %s", exc)

        # 4. Health
        health_api = self._get_api("health")
        if health_api is not None:
            enabled_modules.append("health")
            try:
                h_data = await health_api.get_weekly_metrics(
                    user_id=user_id,
                    since=seven_days_ago,
                )
                health_stats = WeeklyHealthStats(
                    workouts_count=h_data.get("workouts_count", 0),
                    avg_daily_water_ml=h_data.get("avg_daily_water_ml", 0),
                    active_days=h_data.get("active_days", 0),
                )
            except Exception as exc:
                logger.warning("Error fetching health weekly stats: %s", exc)

        summary_obj = WeeklyReviewSummary(
            enabled_modules=enabled_modules,
            study=study_stats,
            habits=habit_stats,
            finance=finance_stats,
            health=health_stats,
            highlights=highlights,
        )

        spoken = format_weekly_review_spoken(summary_obj)
        next_actions = ["what should I study next?", "what are my habits?"]
        return spoken, summary_obj, next_actions
