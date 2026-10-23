"""SQLAlchemy adapter for study plans and daily tasks persistence."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from sahayak.modules.academics.models import PlanTask, StudyPlan


class SQLAlchemyStudyPlanRepository:
    """PostgreSQL SQLAlchemy implementation of StudyPlanPort."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_plan(
        self,
        user_id: uuid.UUID,
        goal: str,
        exam_date: date,
        tasks: Sequence[PlanTask],
    ) -> StudyPlan:
        """Persist a new study plan and its associated initial tasks."""
        plan = StudyPlan(
            id=uuid.uuid4(),
            user_id=user_id,
            goal=goal,
            exam_date=exam_date,
        )
        for task in tasks:
            task.plan_id = plan.id
            plan.tasks.append(task)

        self._session.add(plan)
        await self._session.flush()
        return plan

    async def get_plan(self, plan_id: uuid.UUID, user_id: uuid.UUID) -> StudyPlan | None:
        """Retrieve a study plan ensuring user ownership."""
        stmt = (
            select(StudyPlan)
            .options(selectinload(StudyPlan.tasks))
            .where(StudyPlan.id == plan_id, StudyPlan.user_id == user_id)
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_active_plan(self, user_id: uuid.UUID, as_of: date) -> StudyPlan | None:
        """Fetch the latest active plan for a user whose exam_date >= as_of."""
        stmt = (
            select(StudyPlan)
            .options(selectinload(StudyPlan.tasks))
            .where(StudyPlan.user_id == user_id, StudyPlan.exam_date >= as_of)
            .order_by(StudyPlan.exam_date.asc(), StudyPlan.created_at.desc())
            .limit(1)
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_plans(self, user_id: uuid.UUID, limit: int = 5) -> Sequence[StudyPlan]:
        """List study plans for a user ordered by created_at DESC."""
        stmt = (
            select(StudyPlan)
            .options(selectinload(StudyPlan.tasks))
            .where(StudyPlan.user_id == user_id)
            .order_by(StudyPlan.created_at.desc())
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        return res.scalars().all()

    async def get_tasks_for_date(self, plan_id: uuid.UUID, target_date: date) -> Sequence[PlanTask]:
        """Fetch tasks for a plan on a specific calendar date."""
        stmt = (
            select(PlanTask)
            .where(PlanTask.plan_id == plan_id, PlanTask.date == target_date)
            .order_by(PlanTask.id.asc())
        )
        res = await self._session.execute(stmt)
        return res.scalars().all()

    async def get_task(
        self, task_id: uuid.UUID, plan_id: uuid.UUID | None = None
    ) -> PlanTask | None:
        """Fetch a specific plan task."""
        stmt = select(PlanTask).where(PlanTask.id == task_id)
        if plan_id is not None:
            stmt = stmt.where(PlanTask.plan_id == plan_id)
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def mark_task_done(self, task_id: uuid.UUID, done_at: datetime) -> PlanTask | None:
        """Mark a plan task as completed."""
        stmt = select(PlanTask).where(PlanTask.id == task_id)
        res = await self._session.execute(stmt)
        task = res.scalar_one_or_none()
        if task is not None:
            task.done_at = done_at
            await self._session.flush()
        return task

    async def replace_future_tasks(
        self,
        plan_id: uuid.UUID,
        new_tasks: Sequence[PlanTask],
        from_date: date,
    ) -> Sequence[PlanTask]:
        """Delete incomplete tasks on or after from_date and insert new replanned tasks."""
        del_stmt = delete(PlanTask).where(
            PlanTask.plan_id == plan_id,
            PlanTask.date >= from_date,
            PlanTask.done_at.is_(None),
        )
        await self._session.execute(del_stmt)

        for task in new_tasks:
            task.plan_id = plan_id
            self._session.add(task)

        await self._session.flush()
        return new_tasks
