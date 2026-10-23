"""SQLAlchemy implementation of the HabitRepositoryPort (T5.2)."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from sahayak.modules.productivity.models import Habit, HabitLog


class SQLAlchemyHabitRepository:
    """Repository managing habits and completion logs using SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_habit(
        self,
        user_id: uuid.UUID,
        name: str,
        target_frequency: str = "daily",
    ) -> Habit:
        """Create and persist a new habit."""
        clean_name = name.strip()
        habit = Habit(
            user_id=user_id,
            name=clean_name,
            target_frequency=target_frequency,
            streak_current=0,
            streak_longest=0,
        )
        self.session.add(habit)
        await self.session.flush()
        return habit

    async def get_habit(self, user_id: uuid.UUID, habit_id: uuid.UUID) -> Habit | None:
        """Retrieve habit by ID, scoped by user_id."""
        stmt = (
            select(Habit)
            .where(Habit.id == habit_id, Habit.user_id == user_id)
            .where(Habit.archived_at.is_(None))
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_habit_by_name(self, user_id: uuid.UUID, name: str) -> Habit | None:
        """Retrieve habit by case-insensitive name, scoped by user_id."""
        clean = name.strip().lower()
        stmt = (
            select(Habit)
            .where(Habit.user_id == user_id, func.lower(Habit.name) == clean)
            .where(Habit.archived_at.is_(None))
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_habits(
        self,
        user_id: uuid.UUID,
        include_archived: bool = False,
    ) -> list[Habit]:
        """List habits owned by user."""
        stmt = select(Habit).where(Habit.user_id == user_id)
        if not include_archived:
            stmt = stmt.where(Habit.archived_at.is_(None))
        stmt = stmt.order_by(Habit.created_at.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def log_habit(
        self,
        user_id: uuid.UUID,
        habit_id: uuid.UUID,
        logged_date: date,
        notes: str | None = None,
    ) -> tuple[HabitLog, bool]:
        """Log habit completion on a specific date (ON CONFLICT DO NOTHING for idempotency)."""
        log_id = uuid.uuid4()
        stmt = (
            insert(HabitLog)
            .values(
                id=log_id,
                habit_id=habit_id,
                user_id=user_id,
                logged_date=logged_date,
                notes=notes,
            )
            .on_conflict_do_nothing(constraint="uq_productivity_habit_logs_habit_date")
            .returning(HabitLog)
        )
        result = await self.session.execute(stmt)
        inserted = result.scalars().first()

        if inserted is not None:
            return inserted, True

        # Already logged on this date
        existing_stmt = select(HabitLog).where(
            HabitLog.habit_id == habit_id, HabitLog.logged_date == logged_date
        )
        res_existing = await self.session.execute(existing_stmt)
        existing_log = res_existing.scalars().one()
        return existing_log, False

    async def get_habit_logs(
        self,
        habit_id: uuid.UUID,
        limit: int = 365,
    ) -> list[HabitLog]:
        """Get recent logs for a habit ordered by date descending."""
        stmt = (
            select(HabitLog)
            .where(HabitLog.habit_id == habit_id)
            .order_by(HabitLog.logged_date.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_habit_streak(
        self,
        habit_id: uuid.UUID,
        streak_current: int,
        streak_longest: int,
        last_logged_date: date,
    ) -> Habit | None:
        """Update habit's streak metrics and last completion date."""
        habit = await self.session.get(Habit, habit_id)
        if habit is None:
            return None
        habit.streak_current = streak_current
        habit.streak_longest = streak_longest
        habit.last_logged_date = last_logged_date
        await self.session.flush()
        return habit

    async def archive_habit(
        self,
        user_id: uuid.UUID,
        habit_id: uuid.UUID,
    ) -> Habit | None:
        """Archive a habit."""
        habit = await self.get_habit(user_id, habit_id)
        if habit is None:
            return None
        habit.archived_at = func.now()
        await self.session.flush()
        return habit
