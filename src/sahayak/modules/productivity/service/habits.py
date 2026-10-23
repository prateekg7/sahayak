"""Habit service orchestrating streak calculations, logs, and events (T5.2)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.core.events import publish
from sahayak.modules.productivity.adapters.habits import SQLAlchemyHabitRepository
from sahayak.modules.productivity.domain.habits import (
    calculate_streak,
    format_habit_logged_spoken,
    format_habits_list_spoken,
    resolve_local_date,
)
from sahayak.modules.productivity.schemas import HabitData, HabitsResponseData


class HabitService:
    """Service orchestrating habit operations, streak computation, and event dispatching."""

    def __init__(
        self,
        session_factory: Any,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.clock = clock or (lambda: datetime.now(ZoneInfo("UTC")))

    def _now(self) -> datetime:
        return self.clock()

    def _parse_id(self, raw_id: str | None) -> uuid.UUID | None:
        if not raw_id:
            return None
        try:
            return uuid.UUID(raw_id)
        except (ValueError, TypeError) as err:
            raise InvalidInputError(f"Invalid UUID '{raw_id}'") from err

    async def create_habit(
        self,
        user_id: uuid.UUID,
        name: str | None,
        frequency: str = "daily",
    ) -> tuple[str, HabitsResponseData, list[str]]:
        if not name or not name.strip():
            raise InvalidInputError("Habit name cannot be empty")

        clean_name = name.strip()
        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyHabitRepository(uow.session)
            existing = await repo.get_habit_by_name(user_id, clean_name)
            if existing is not None:
                habit = existing
            else:
                habit = await repo.create_habit(
                    user_id=user_id,
                    name=clean_name,
                    target_frequency=frequency,
                )
            habit_dict = habit.to_dict()

        spoken = f"Started tracking {habit.name}. Say 'log {habit.name}' when complete!"
        data = HabitsResponseData(
            action="create",
            habit=HabitData(**habit_dict),
            count=1,
        )
        next_actions = [f"log {habit.name}", "what are my habits?"]
        return spoken, data, next_actions

    async def log_habit(
        self,
        user_id: uuid.UUID,
        name: str | None = None,
        habit_id_str: str | None = None,
        date_str: str | None = None,
        timezone_str: str = "UTC",
    ) -> tuple[str, HabitsResponseData, list[str]]:
        habit_id = self._parse_id(habit_id_str)
        if not habit_id and (not name or not name.strip()):
            raise InvalidInputError("Please specify a habit name or ID to log")

        local_today = resolve_local_date(self._now(), timezone_str)
        target_date = local_today
        if date_str:
            try:
                target_date = date.fromisoformat(date_str)
            except ValueError as err:
                msg = f"Invalid date format '{date_str}'; use YYYY-MM-DD"
                raise InvalidInputError(msg) from err

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyHabitRepository(uow.session)
            if habit_id:
                habit = await repo.get_habit(user_id, habit_id)
            elif name:
                habit = await repo.get_habit_by_name(user_id, name)
            else:
                habit = None

            if habit is None:
                target_desc = habit_id_str or name
                raise NotFoundError(f"Habit '{target_desc}' not found. Say add habit to create it.")

            # Log completion on target date
            _, was_new = await repo.log_habit(
                user_id=user_id,
                habit_id=habit.id,
                logged_date=target_date,
            )

            # Query all logs to recompute streak accurately
            logs = await repo.get_habit_logs(habit.id, limit=365)
            log_dates = [log.logged_date for log in logs]
            curr_streak, long_streak = calculate_streak(log_dates, local_today)

            prev_longest = habit.streak_longest
            updated_habit = await repo.update_habit_streak(
                habit_id=habit.id,
                streak_current=curr_streak,
                streak_longest=long_streak,
                last_logged_date=target_date,
            )
            habit_dict = updated_habit.to_dict() if updated_habit else habit.to_dict()

            # Publish domain event for cross-module integration
            publish(
                session=uow.session,
                aggregate="habit",
                type="habit.completed",
                payload={
                    "user_id": str(user_id),
                    "habit_id": str(habit.id),
                    "name": habit.name,
                    "streak": curr_streak,
                    "date": target_date.isoformat(),
                },
            )

        is_new_record = curr_streak > prev_longest and curr_streak > 1
        spoken = format_habit_logged_spoken(habit.name, curr_streak, is_new_record)
        data = HabitsResponseData(
            action="log",
            habit=HabitData(**habit_dict),
            count=1,
        )
        next_actions = ["what are my habits?"]
        return spoken, data, next_actions

    async def get_habit_status(
        self,
        user_id: uuid.UUID,
        name: str | None = None,
        habit_id_str: str | None = None,
        timezone_str: str = "UTC",
    ) -> tuple[str, HabitsResponseData, list[str]]:
        habit_id = self._parse_id(habit_id_str)
        if not habit_id and (not name or not name.strip()):
            raise InvalidInputError("Please specify a habit name or ID")

        local_today = resolve_local_date(self._now(), timezone_str)

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyHabitRepository(uow.session)
            if habit_id:
                habit = await repo.get_habit(user_id, habit_id)
            elif name:
                habit = await repo.get_habit_by_name(user_id, name)
            else:
                habit = None

            if habit is None:
                target_desc = habit_id_str or name
                raise NotFoundError(f"Habit '{target_desc}' not found.")

            logs = await repo.get_habit_logs(habit.id, limit=365)
            log_dates = [log.logged_date for log in logs]
            curr_streak, long_streak = calculate_streak(log_dates, local_today)
            habit_dict = habit.to_dict()
            habit_dict["streak_current"] = curr_streak
            habit_dict["streak_longest"] = long_streak

        done_today = local_today in set(log_dates)
        status_suffix = "Completed today!" if done_today else "Not logged today yet."
        spoken = (
            f"{habit.name} is on a {curr_streak} day streak with a best of {long_streak} days. "
            f"{status_suffix}"
        )
        data = HabitsResponseData(
            action="status",
            habit=HabitData(**habit_dict),
            count=1,
        )
        next_actions = [f"log {habit.name}"] if not done_today else ["what are my habits?"]
        return spoken, data, next_actions

    async def list_habits(
        self,
        user_id: uuid.UUID,
        timezone_str: str = "UTC",
    ) -> tuple[str, HabitsResponseData, list[str]]:
        local_today = resolve_local_date(self._now(), timezone_str)

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyHabitRepository(uow.session)
            habits = await repo.list_habits(user_id)
            habit_dicts: list[dict[str, Any]] = []
            for h in habits:
                logs = await repo.get_habit_logs(h.id, limit=60)
                curr, longest = calculate_streak([entry.logged_date for entry in logs], local_today)
                d = h.to_dict()
                d["streak_current"] = curr
                d["streak_longest"] = longest
                habit_dicts.append(d)

        spoken = format_habits_list_spoken(habit_dicts)
        data = HabitsResponseData(
            action="list",
            habits=[HabitData(**d) for d in habit_dicts],
            count=len(habit_dicts),
        )
        next_actions = ["log habit", "add a habit"]
        return spoken, data, next_actions
