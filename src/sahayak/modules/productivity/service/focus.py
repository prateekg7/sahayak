"""Focus timer service orchestrating sessions, remaining time calculation, and history (T5.4)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import NotFoundError
from sahayak.modules.productivity.adapters.focus import SQLAlchemyFocusRepository
from sahayak.modules.productivity.domain.focus import (
    calculate_session_remaining,
    format_history_spoken,
    format_session_start_spoken,
    format_session_status_spoken,
    format_session_stop_spoken,
    validate_duration_minutes,
)
from sahayak.modules.productivity.schemas import (
    FocusResponseData,
    FocusSessionData,
    FocusStatsData,
)


class FocusService:
    """Service managing focus timer sessions and history with transaction isolation."""

    def __init__(
        self,
        session_factory: Any,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        dt = self.clock()
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)

    def _resolve_timezone(self, tz_name: str) -> ZoneInfo:
        try:
            return ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, ValueError):
            return ZoneInfo("UTC")

    async def start_session(
        self,
        user_id: uuid.UUID,
        duration_minutes: int = 25,
        task_label: str | None = None,
    ) -> tuple[str, FocusResponseData, list[str]]:
        validated_duration = validate_duration_minutes(duration_minutes)
        now = self._now()

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyFocusRepository(uow.session)
            active = await repo.get_active_session(user_id)

            if active is not None:
                rem_sec, is_active, should_complete = calculate_session_remaining(
                    active.planned_end_at, now, active.status
                )
                if should_complete:
                    await repo.update_session_status(
                        active.id,
                        status="completed",
                        actual_end_at=active.planned_end_at,
                    )
                elif is_active:
                    rem_min = (rem_sec + 59) // 60
                    spoken = (
                        f"You already have an active focus session with {rem_min} "
                        "minutes remaining. Say how much time is left or stop focus session."
                    )
                    session_dict = active.to_dict()
                    session_dict["remaining_seconds"] = rem_sec
                    data = FocusResponseData(
                        action="start",
                        session=FocusSessionData(**session_dict),
                    )
                    return spoken, data, ["how much time is left", "stop focus session"]

            # Start fresh session
            planned_end = now + timedelta(minutes=validated_duration)
            session = await repo.create_session(
                user_id=user_id,
                duration_minutes=validated_duration,
                started_at=now,
                planned_end_at=planned_end,
                task_label=task_label,
            )
            session_dict = session.to_dict()
            session_dict["remaining_seconds"] = validated_duration * 60

        spoken = format_session_start_spoken(validated_duration, task_label)
        data = FocusResponseData(
            action="start",
            session=FocusSessionData(**session_dict),
        )
        next_actions = ["how much time is left", "stop focus session"]
        return spoken, data, next_actions

    async def get_session_status(
        self,
        user_id: uuid.UUID,
    ) -> tuple[str, FocusResponseData, list[str]]:
        now = self._now()

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyFocusRepository(uow.session)
            active = await repo.get_active_session(user_id)

            if active is None:
                spoken = (
                    "You do not have an active focus session right now. "
                    "Say start a 25 minute focus session to begin."
                )
                data = FocusResponseData(action="status")
                return spoken, data, ["start a 25 minute focus session"]

            rem_sec, is_active, should_complete = calculate_session_remaining(
                active.planned_end_at, now, active.status
            )
            if should_complete:
                await repo.update_session_status(
                    active.id,
                    status="completed",
                    actual_end_at=active.planned_end_at,
                )
                session_dict = active.to_dict()
                session_dict["status"] = "completed"
                session_dict["remaining_seconds"] = 0
                spoken = format_session_status_spoken(
                    0, active.duration_minutes, active.task_label, is_completed=True
                )
                data = FocusResponseData(
                    action="status",
                    session=FocusSessionData(**session_dict),
                )
                return spoken, data, ["start a 25 minute focus session", "focus history"]

            session_dict = active.to_dict()
            session_dict["remaining_seconds"] = rem_sec
            spoken = format_session_status_spoken(
                rem_sec, active.duration_minutes, active.task_label, is_completed=False
            )
            data = FocusResponseData(
                action="status",
                session=FocusSessionData(**session_dict),
            )
            return spoken, data, ["how much time is left", "stop focus session"]

    async def stop_session(
        self,
        user_id: uuid.UUID,
    ) -> tuple[str, FocusResponseData, list[str]]:
        now = self._now()

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyFocusRepository(uow.session)
            active = await repo.get_active_session(user_id)

            if active is None:
                raise NotFoundError("You do not have an active focus session to stop.")

            elapsed_minutes = max(0, int((now - active.started_at).total_seconds() // 60))
            is_past_end = now >= active.planned_end_at
            new_status = "completed" if is_past_end else "cancelled"

            updated = await repo.update_session_status(
                active.id,
                status=new_status,
                actual_end_at=now,
            )
            if updated is None:
                raise NotFoundError("Failed to update focus session.")

            session_dict = updated.to_dict()
            session_dict["remaining_seconds"] = 0

        spoken = format_session_stop_spoken(elapsed_minutes, active.task_label)
        data = FocusResponseData(
            action="stop",
            session=FocusSessionData(**session_dict),
        )
        next_actions = ["start a 25 minute focus session", "focus history"]
        return spoken, data, next_actions

    async def get_history(
        self,
        user_id: uuid.UUID,
        limit: int = 10,
        timezone_str: str = "UTC",
    ) -> tuple[str, FocusResponseData, list[str]]:
        now = self._now()
        tz = self._resolve_timezone(timezone_str)
        local_now = now.astimezone(tz)
        start_of_day = datetime(
            local_now.year, local_now.month, local_now.day, tzinfo=tz
        ).astimezone(UTC)

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyFocusRepository(uow.session)
            total_completed, total_minutes, today_completed = await repo.get_session_stats(
                user_id=user_id,
                since_today=start_of_day,
            )
            sessions = await repo.list_sessions(user_id, limit=limit)
            sessions_data = [FocusSessionData(**s.to_dict()) for s in sessions]

        spoken = format_history_spoken(total_completed, total_minutes, today_completed)
        stats = FocusStatsData(
            total_completed=total_completed,
            total_minutes_focused=total_minutes,
            today_completed=today_completed,
        )
        data = FocusResponseData(
            action="history",
            sessions=sessions_data,
            stats=stats,
        )
        next_actions = ["start a 25 minute focus session"]
        return spoken, data, next_actions
