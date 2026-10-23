"""Service for exam study plans and daily task management."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sahayak.core.db.session import SessionFactory
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.academics.adapters.study_plans import SQLAlchemyStudyPlanRepository
from sahayak.modules.academics.domain.planner import (
    generate_study_plan,
    parse_exam_date,
    resolve_current_date,
)
from sahayak.modules.academics.models import PlanTask
from sahayak.modules.academics.schemas import (
    PlanTaskData,
    StudyPlanResponseData,
    StudyPlanSummaryData,
)
from sahayak.shared.llm.ports import LLMClient

logger = logging.getLogger(__name__)


class RawTopicBreakdownOutput(BaseModel):
    """Pydantic model for structured LLM topic breakdown output."""

    topics: list[str] = Field(default_factory=list)


class StudyPlanService:
    """Coordinates study plan creation, daily task retrieval, and schedule replanning."""

    def __init__(
        self,
        session_factory: SessionFactory | async_sessionmaker[AsyncSession] | Any,
        llm_client: LLMClient | None = None,
        prompt_path: Path | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._llm = llm_client
        default_prompt = Path("prompts/topic_breakdown_v1.md")
        if not default_prompt.is_file():
            default_prompt = (
                Path(__file__).resolve().parents[5] / "prompts" / "topic_breakdown_v1.md"
            )
        self._prompt_path = prompt_path or default_prompt
        self._prompt_template: str | None = None
        self._clock = clock or (lambda: datetime.now(UTC))

    def _load_prompt_template(self) -> str:
        if self._prompt_template is None:
            if not self._prompt_path.is_file():
                msg = f"Missing topic breakdown prompt at {self._prompt_path}"
                raise FileNotFoundError(msg)
            self._prompt_template = self._prompt_path.read_text(encoding="utf-8")
        return self._prompt_template

    async def break_down_goal(self, goal: str) -> list[str]:
        """Break down a subject or goal into key study topics via LLM."""
        cleaned_goal = goal.strip()
        if self._llm is None:
            return [cleaned_goal]

        template = self._load_prompt_template()
        prompt = template.format(goal=cleaned_goal)
        try:
            res = await self._llm.generate_json(
                prompt=prompt,
                schema=RawTopicBreakdownOutput,
                temperature=0.4,
                max_tokens=500,
            )
            if isinstance(res.parsed, RawTopicBreakdownOutput):
                parsed = res.parsed
            elif isinstance(res.parsed, dict):
                parsed = RawTopicBreakdownOutput.model_validate(res.parsed)
            else:
                parsed = RawTopicBreakdownOutput.model_validate_json(res.content)

            topics = [t.strip() for t in parsed.topics if t.strip() and len(t.strip()) <= 100]
            if topics:
                return topics[:6]
        except Exception as err:
            logger.warning("Topic breakdown LLM generation failed for '%s': %s", cleaned_goal, err)

        return [cleaned_goal]

    async def create_study_plan(
        self,
        user_id: uuid.UUID,
        goal: str,
        exam_date_str: str,
        topics: Sequence[str] | None = None,
        hours_per_day: float = 1.0,
        timezone: str = "UTC",
    ) -> tuple[StudyPlanResponseData, str]:
        """Create a new exam study plan with day-by-day scheduled study tasks."""
        cleaned_goal = goal.strip()
        if not cleaned_goal:
            msg = "Goal cannot be empty."
            raise InvalidInputError(msg)
        if len(cleaned_goal) > 256:
            msg = "Goal cannot exceed 256 characters."
            raise InvalidInputError(msg)

        current_date = resolve_current_date(self._clock, user_timezone=timezone)

        try:
            target_exam_date = parse_exam_date(exam_date_str, current_date)
        except ValueError as err:
            raise InvalidInputError(str(err)) from err

        clean_topics = [t.strip() for t in topics if t.strip()] if topics else []
        if not clean_topics:
            clean_topics = await self.break_down_goal(cleaned_goal)

        schedule = generate_study_plan(
            exam_date=target_exam_date,
            topics=clean_topics,
            hours_per_day=hours_per_day,
            start_date=current_date,
            user_timezone=timezone,
            clock=self._clock,
        )

        db_tasks = [
            PlanTask(
                id=uuid.uuid4(),
                date=t.date,
                topic=t.topic,
                minutes=t.minutes,
                done_at=None,
            )
            for t in schedule.tasks
        ]

        async with self._session_factory() as session:
            repo = SQLAlchemyStudyPlanRepository(session)
            plan = await repo.create_plan(
                user_id=user_id,
                goal=cleaned_goal,
                exam_date=target_exam_date,
                tasks=db_tasks,
            )
            await session.commit()
            plan_id_str = str(plan.id)

        task_data_list = [
            PlanTaskData(
                task_id=str(t.id),
                date=t.date.isoformat(),
                topic=t.topic,
                minutes=t.minutes,
                done=False,
                done_at=None,
            )
            for t in db_tasks
        ]

        today_tasks = [t for t in task_data_list if t.date == current_date.isoformat()]

        date_formatted = target_exam_date.strftime("%B %d")
        if today_tasks:
            spoken_summary = (
                f"I created your study plan for {cleaned_goal} with {len(task_data_list)} "
                f"tasks until {date_formatted}. Today's task is {today_tasks[0].topic} "
                f"for {today_tasks[0].minutes} minutes."
            )
        else:
            spoken_summary = (
                f"I created your study plan for {cleaned_goal} with {len(task_data_list)} "
                f"tasks across {schedule.total_days} days until {date_formatted}."
            )

        if not schedule.is_feasible and schedule.warning:
            spoken_summary += f" Note: {schedule.warning}"

        if len(spoken_summary) > 300:
            spoken_summary = (
                f"I created your study plan for {cleaned_goal} with {len(task_data_list)} "
                f"tasks until {date_formatted}."
            )

        response_data = StudyPlanResponseData(
            action="create",
            plan_id=plan_id_str,
            goal=cleaned_goal,
            exam_date=target_exam_date.isoformat(),
            today_tasks=today_tasks,
            tasks=task_data_list,
            total_days=schedule.total_days,
            daily_minutes=schedule.daily_minutes_capacity,
            is_feasible=schedule.is_feasible,
            warning_message=schedule.warning,
        )

        return response_data, spoken_summary

    async def get_today_tasks(
        self,
        user_id: uuid.UUID,
        plan_id: uuid.UUID | None = None,
        timezone: str = "UTC",
    ) -> tuple[StudyPlanResponseData, str]:
        """Fetch today's planned study tasks for the active or requested plan."""
        current_date = resolve_current_date(self._clock, user_timezone=timezone)

        async with self._session_factory() as session:
            repo = SQLAlchemyStudyPlanRepository(session)
            if plan_id is not None:
                plan = await repo.get_plan(plan_id, user_id)
                if plan is None:
                    msg = f"Study plan '{plan_id}' not found."
                    raise NotFoundError(msg)
            else:
                plan = await repo.get_active_plan(user_id, as_of=current_date)
                if plan is None:
                    spoken = (
                        "You do not have an active study plan. "
                        "Say 'make a study plan' to create one."
                    )
                    return StudyPlanResponseData(action="today", today_tasks=[]), spoken

            tasks = await repo.get_tasks_for_date(plan.id, current_date)
            plan_id_str = str(plan.id)
            goal = plan.goal
            exam_date_str = plan.exam_date.isoformat()

        today_data = [
            PlanTaskData(
                task_id=str(t.id),
                date=t.date.isoformat(),
                topic=t.topic,
                minutes=t.minutes,
                done=t.done_at is not None,
                done_at=t.done_at.isoformat() if t.done_at else None,
            )
            for t in tasks
        ]

        incomplete = [t for t in today_data if not t.done]
        if not today_data:
            spoken_summary = (
                f"You have no study tasks scheduled for today for {goal}. "
                "Enjoy your rest or review previous notes."
            )
        elif not incomplete:
            spoken_summary = (
                f"You have completed all {len(today_data)} tasks scheduled for today. Great job!"
            )
        else:
            task_desc = ", ".join(f"{t.topic} for {t.minutes} minutes" for t in incomplete[:2])
            spoken_summary = (
                f"Today you have {len(incomplete)} study task{'s' if len(incomplete) > 1 else ''}: "
                f"{task_desc}. Say 'mark done' when finished."
            )

        if len(spoken_summary) > 300:
            spoken_summary = (
                f"Today you have {len(incomplete)} tasks scheduled for {goal}. "
                "Say 'mark done' when finished."
            )

        response_data = StudyPlanResponseData(
            action="today",
            plan_id=plan_id_str,
            goal=goal,
            exam_date=exam_date_str,
            today_tasks=today_data,
        )

        return response_data, spoken_summary

    async def update_plan(
        self,
        user_id: uuid.UUID,
        plan_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        mark_done: bool | None = None,
        replan: bool = False,
        hours_per_day: float | None = None,
        timezone: str = "UTC",
    ) -> tuple[StudyPlanResponseData, str]:
        """Update a study plan by marking a task done or replanning remaining days."""
        current_date = resolve_current_date(self._clock, user_timezone=timezone)

        async with self._session_factory() as session:
            repo = SQLAlchemyStudyPlanRepository(session)

            # Resolve plan
            if plan_id is not None:
                plan = await repo.get_plan(plan_id, user_id)
            elif task_id is not None:
                task = await repo.get_task(task_id)
                if task is None:
                    msg = f"Task '{task_id}' not found."
                    raise NotFoundError(msg)
                plan = await repo.get_plan(task.plan_id, user_id)
            else:
                plan = await repo.get_active_plan(user_id, as_of=current_date)

            if plan is None:
                msg = "No active study plan found."
                raise NotFoundError(msg)

            # Case A: Mark task done
            if mark_done and task_id is not None:
                task = await repo.get_task(task_id, plan.id)
                if task is None:
                    msg = f"Task '{task_id}' not found in study plan."
                    raise NotFoundError(msg)

                now_utc = self._clock()
                updated_task = await repo.mark_task_done(task.id, now_utc)
                await session.commit()

                if updated_task is None:
                    msg = f"Failed to mark task '{task_id}' done."
                    raise NotFoundError(msg)

                task_data = PlanTaskData(
                    task_id=str(updated_task.id),
                    date=updated_task.date.isoformat(),
                    topic=updated_task.topic,
                    minutes=updated_task.minutes,
                    done=True,
                    done_at=updated_task.done_at.isoformat() if updated_task.done_at else None,
                )
                spoken = f"Marked '{updated_task.topic}' as completed. Great progress!"
                return (
                    StudyPlanResponseData(
                        action="update",
                        plan_id=str(plan.id),
                        goal=plan.goal,
                        exam_date=plan.exam_date.isoformat(),
                        updated_task=task_data,
                    ),
                    spoken,
                )

            # Case B: Replan remaining days
            if replan:
                existing_tasks = list(plan.tasks)
                completed_topics = {t.topic for t in existing_tasks if t.done_at is not None}
                incomplete_topics = [
                    t.topic
                    for t in existing_tasks
                    if t.done_at is None and t.topic not in completed_topics
                ]
                # If all topics completed, schedule practice/review
                remaining_topics = (
                    incomplete_topics if incomplete_topics else [f"{plan.goal} Practice and Review"]
                )

                effective_hours = hours_per_day or 1.0
                new_schedule = generate_study_plan(
                    exam_date=plan.exam_date,
                    topics=remaining_topics,
                    hours_per_day=effective_hours,
                    start_date=current_date,
                    user_timezone=timezone,
                    clock=self._clock,
                )

                new_db_tasks = [
                    PlanTask(
                        id=uuid.uuid4(),
                        date=t.date,
                        topic=t.topic,
                        minutes=t.minutes,
                        done_at=None,
                    )
                    for t in new_schedule.tasks
                ]

                replaced = await repo.replace_future_tasks(
                    plan.id, new_db_tasks, from_date=current_date
                )
                await session.commit()

                task_data_list = [
                    PlanTaskData(
                        task_id=str(t.id),
                        date=t.date.isoformat(),
                        topic=t.topic,
                        minutes=t.minutes,
                        done=False,
                        done_at=None,
                    )
                    for t in replaced
                ]

                spoken = (
                    f"I have replanned your schedule for {plan.goal}. "
                    f"You have {len(task_data_list)} remaining tasks across "
                    f"{new_schedule.total_days} days until {plan.exam_date.strftime('%B %d')}."
                )
                if len(spoken) > 300:
                    spoken = (
                        f"I have replanned your schedule with {len(task_data_list)} "
                        f"remaining tasks until {plan.exam_date.strftime('%B %d')}."
                    )

                return (
                    StudyPlanResponseData(
                        action="update",
                        plan_id=str(plan.id),
                        goal=plan.goal,
                        exam_date=plan.exam_date.isoformat(),
                        tasks=task_data_list,
                        total_days=new_schedule.total_days,
                        daily_minutes=new_schedule.daily_minutes_capacity,
                        is_feasible=new_schedule.is_feasible,
                        warning_message=new_schedule.warning,
                    ),
                    spoken,
                )

            msg = (
                "Update action requires either 'mark_done: true' with 'task_id', or 'replan: true'."
            )
            raise InvalidInputError(msg)

    async def list_plans(
        self,
        user_id: uuid.UUID,
        limit: int = 5,
    ) -> tuple[StudyPlanResponseData, str]:
        """List study plans belonging to the user."""
        async with self._session_factory() as session:
            repo = SQLAlchemyStudyPlanRepository(session)
            plans = await repo.list_plans(user_id, limit=limit)

            summaries: list[StudyPlanSummaryData] = []
            for plan in plans:
                total_tasks = len(plan.tasks)
                completed_tasks = sum(1 for t in plan.tasks if t.done_at is not None)
                summaries.append(
                    StudyPlanSummaryData(
                        plan_id=str(plan.id),
                        goal=plan.goal,
                        exam_date=plan.exam_date.isoformat(),
                        total_tasks=total_tasks,
                        completed_tasks=completed_tasks,
                        created_at=plan.created_at.isoformat(),
                    )
                )

        if not summaries:
            spoken = "You have no study plans yet. Say 'make a study plan' to create one."
        else:
            first = summaries[0]
            spoken = (
                f"You have {len(summaries)} study plan{'s' if len(summaries) > 1 else ''}. "
                f"Most recent is {first.goal} with {first.completed_tasks} of {first.total_tasks} "
                "tasks completed."
            )

        if len(spoken) > 300:
            spoken = f"You have {len(summaries)} study plans."

        return StudyPlanResponseData(action="list", plans=summaries), spoken
