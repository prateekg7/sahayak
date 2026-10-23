"""Application service orchestrating health summary and medicine tracking (T7.2).

Tracking personal habits and schedules only; zero medical or dosing advice provided (PRD §1.4).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.health.adapters.entries import SQLAlchemyHealthRepository
from sahayak.modules.health.adapters.medicines import SQLAlchemyMedicineRepository
from sahayak.modules.health.domain.entries import HEALTH_DISCLAIMER
from sahayak.modules.health.domain.summary import (
    calculate_today_summary,
    calculate_weekly_summary,
    format_health_today_spoken,
    format_health_week_spoken,
    format_medicine_added_spoken,
    format_medicine_marked_spoken,
    format_medicines_due_spoken,
    is_medicine_scheduled_on_date,
)
from sahayak.modules.health.schemas import (
    HealthSummaryRequest,
    HealthSummaryResponseData,
    MedicineDueData,
    MedicineScheduleData,
)


class HealthSummaryService:
    """Service managing periodic health summaries, metrics aggregation, and medicine adherence."""

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

    def _today(self) -> date:
        return self._now().date()

    async def execute(
        self,
        user_id: uuid.UUID,
        request: HealthSummaryRequest,
    ) -> tuple[HealthSummaryResponseData, str]:
        """Dispatch summary and medicine actions."""
        action = request.action.value if hasattr(request.action, "value") else str(request.action)

        if action == "today":
            return await self._handle_today(user_id, request)
        if action == "week":
            return await self._handle_week(user_id, request)
        if action == "medicines_due":
            return await self._handle_medicines_due(user_id, request)
        if action == "mark_taken":
            return await self._handle_mark_taken(user_id, request)
        if action == "add_medicine":
            return await self._handle_add_medicine(user_id, request)
        if action == "list_medicines":
            return await self._handle_list_medicines(user_id, request)

        raise InvalidInputError(
            f"Unknown action: {action}. Expected 'today', 'week', 'medicines_due', "
            "'mark_taken', 'add_medicine', or 'list_medicines'."
        )

    async def _handle_today(
        self,
        user_id: uuid.UUID,
        request: HealthSummaryRequest,
    ) -> tuple[HealthSummaryResponseData, str]:
        today_date = self._today()
        start_dt = datetime.combine(today_date, time.min, tzinfo=UTC)
        end_dt = datetime.combine(today_date, time.max, tzinfo=UTC)

        async with UnitOfWork(self.session_factory) as uow:
            h_repo = SQLAlchemyHealthRepository(uow.session)
            m_repo = SQLAlchemyMedicineRepository(uow.session)

            entries = await h_repo.list_entries(
                user_id=user_id,
                since=start_dt,
                until=end_dt,
                limit=100,
            )
            meds = await m_repo.list_medicines(user_id=user_id, is_active=True)
            doses = await m_repo.list_doses_for_date(user_id=user_id, scheduled_date=today_date)

        # Evaluate scheduled doses for today
        scheduled_count = 0
        dose_map = {(str(d.medicine_id), d.scheduled_time): d for d in doses}
        due_items: list[MedicineDueData] = []

        for m in meds:
            if is_medicine_scheduled_on_date(m.start_date, m.end_date, m.days, today_date):
                times = m.times if m.times else ["09:00"]
                for t_str in times:
                    scheduled_count += 1
                    existing_dose = dose_map.get((str(m.id), t_str))
                    status = existing_dose.status if existing_dose else "pending"
                    taken_at = (
                        existing_dose.taken_at.isoformat()
                        if existing_dose and existing_dose.taken_at
                        else None
                    )
                    due_items.append(
                        MedicineDueData(
                            id=str(existing_dose.id) if existing_dose else str(uuid.uuid4()),
                            medicine_id=str(m.id),
                            name=m.name,
                            dosage_text=m.dosage_text,
                            scheduled_date=today_date.isoformat(),
                            scheduled_time=t_str,
                            status=status,
                            taken_at=taken_at,
                        )
                    )

        taken_count = sum(1 for item in due_items if item.status == "taken")
        entries_dicts = [e.to_dict() for e in entries]
        summary = calculate_today_summary(entries_dicts, scheduled_count, taken_count)
        spoken = format_health_today_spoken(summary)

        return (
            HealthSummaryResponseData(
                action="today",
                period=today_date.isoformat(),
                summary=summary,
                medicines_due=due_items,
                disclaimer=HEALTH_DISCLAIMER,
            ),
            spoken,
        )

    async def _handle_week(
        self,
        user_id: uuid.UUID,
        request: HealthSummaryRequest,
    ) -> tuple[HealthSummaryResponseData, str]:
        today_date = self._today()
        start_date = today_date - timedelta(days=6)
        start_dt = datetime.combine(start_date, time.min, tzinfo=UTC)
        end_dt = datetime.combine(today_date, time.max, tzinfo=UTC)

        async with UnitOfWork(self.session_factory) as uow:
            h_repo = SQLAlchemyHealthRepository(uow.session)
            m_repo = SQLAlchemyMedicineRepository(uow.session)

            entries = await h_repo.list_entries(
                user_id=user_id,
                since=start_dt,
                until=end_dt,
                limit=500,
            )
            meds = await m_repo.list_medicines(user_id=user_id, is_active=True)
            doses = await m_repo.list_doses_in_range(
                user_id=user_id, start_date=start_date, end_date=today_date
            )

        # Count total scheduled doses over the 7 days
        total_scheduled = 0
        curr = start_date
        while curr <= today_date:
            for m in meds:
                if is_medicine_scheduled_on_date(m.start_date, m.end_date, m.days, curr):
                    times = m.times if m.times else ["09:00"]
                    total_scheduled += len(times)
            curr += timedelta(days=1)

        total_taken = sum(1 for d in doses if d.status == "taken")
        entries_dicts = [e.to_dict() for e in entries]
        summary = calculate_weekly_summary(entries_dicts, total_scheduled, total_taken)
        spoken = format_health_week_spoken(summary)

        return (
            HealthSummaryResponseData(
                action="week",
                period=f"{start_date.isoformat()}_to_{today_date.isoformat()}",
                summary=summary,
                disclaimer=HEALTH_DISCLAIMER,
            ),
            spoken,
        )

    async def _handle_medicines_due(
        self,
        user_id: uuid.UUID,
        request: HealthSummaryRequest,
    ) -> tuple[HealthSummaryResponseData, str]:
        today_date = self._today()
        async with UnitOfWork(self.session_factory) as uow:
            m_repo = SQLAlchemyMedicineRepository(uow.session)
            meds = await m_repo.list_medicines(user_id=user_id, is_active=True)
            doses = await m_repo.list_doses_for_date(user_id=user_id, scheduled_date=today_date)

        dose_map = {(str(d.medicine_id), d.scheduled_time): d for d in doses}
        due_items: list[MedicineDueData] = []

        for m in meds:
            if is_medicine_scheduled_on_date(m.start_date, m.end_date, m.days, today_date):
                times = m.times if m.times else ["09:00"]
                for t_str in times:
                    existing_dose = dose_map.get((str(m.id), t_str))
                    status = existing_dose.status if existing_dose else "pending"
                    taken_at = (
                        existing_dose.taken_at.isoformat()
                        if existing_dose and existing_dose.taken_at
                        else None
                    )
                    due_items.append(
                        MedicineDueData(
                            id=str(existing_dose.id) if existing_dose else str(uuid.uuid4()),
                            medicine_id=str(m.id),
                            name=m.name,
                            dosage_text=m.dosage_text,
                            scheduled_date=today_date.isoformat(),
                            scheduled_time=t_str,
                            status=status,
                            taken_at=taken_at,
                        )
                    )

        spoken = format_medicines_due_spoken([d.model_dump() for d in due_items])
        return (
            HealthSummaryResponseData(
                action="medicines_due",
                period=today_date.isoformat(),
                medicines_due=due_items,
                disclaimer=HEALTH_DISCLAIMER,
            ),
            spoken,
        )

    async def _handle_mark_taken(
        self,
        user_id: uuid.UUID,
        request: HealthSummaryRequest,
    ) -> tuple[HealthSummaryResponseData, str]:
        if not request.medicine_name or not request.medicine_name.strip():
            raise InvalidInputError("Medicine name is required to mark a dose as taken.")

        today_date = self._today()
        now_dt = self._now()

        async with UnitOfWork(self.session_factory) as uow:
            m_repo = SQLAlchemyMedicineRepository(uow.session)
            med = await m_repo.find_medicine_by_name(user_id, request.medicine_name)
            if med is None:
                raise NotFoundError(
                    f"No active medicine schedule found for '{request.medicine_name}'."
                )

            sched_time = request.scheduled_time or (med.times[0] if med.times else "09:00")
            dose = await m_repo.record_or_update_dose(
                user_id=user_id,
                medicine_id=med.id,
                scheduled_date=today_date,
                scheduled_time=sched_time,
                status="taken",
                taken_at=now_dt,
            )

        spoken = format_medicine_marked_spoken(med.name, sched_time)
        due_item = MedicineDueData(
            id=str(dose.id),
            medicine_id=str(med.id),
            name=med.name,
            dosage_text=med.dosage_text,
            scheduled_date=today_date.isoformat(),
            scheduled_time=sched_time,
            status="taken",
            taken_at=now_dt.isoformat(),
        )

        return (
            HealthSummaryResponseData(
                action="mark_taken",
                medicines_due=[due_item],
                disclaimer=HEALTH_DISCLAIMER,
            ),
            spoken,
        )

    async def _handle_add_medicine(
        self,
        user_id: uuid.UUID,
        request: HealthSummaryRequest,
    ) -> tuple[HealthSummaryResponseData, str]:
        if not request.medicine_name or not request.medicine_name.strip():
            raise InvalidInputError("Medicine name is required.")

        today_date = self._today()
        times = request.times or ([request.scheduled_time] if request.scheduled_time else ["09:00"])

        async with UnitOfWork(self.session_factory) as uow:
            m_repo = SQLAlchemyMedicineRepository(uow.session)
            med = await m_repo.create_medicine(
                user_id=user_id,
                name=request.medicine_name,
                dosage_text=request.dosage_text or "1 dose",
                times=times,
                days=request.days,
                start_date=today_date,
            )

        spoken = format_medicine_added_spoken(med.name, times)
        sched_dto = MedicineScheduleData(
            id=str(med.id),
            name=med.name,
            dosage_text=med.dosage_text,
            times=med.times,
            days=med.days,
            is_active=med.is_active,
        )

        return (
            HealthSummaryResponseData(
                action="add_medicine",
                medicines=[sched_dto],
                disclaimer=HEALTH_DISCLAIMER,
            ),
            spoken,
        )

    async def _handle_list_medicines(
        self,
        user_id: uuid.UUID,
        request: HealthSummaryRequest,
    ) -> tuple[HealthSummaryResponseData, str]:
        async with UnitOfWork(self.session_factory) as uow:
            m_repo = SQLAlchemyMedicineRepository(uow.session)
            meds = await m_repo.list_medicines(user_id=user_id, is_active=True)

        dtos = [
            MedicineScheduleData(
                id=str(m.id),
                name=m.name,
                dosage_text=m.dosage_text,
                times=m.times,
                days=m.days,
                is_active=m.is_active,
            )
            for m in meds
        ]
        if not dtos:
            spoken = "You have no active medicine schedules."
        else:
            names = ", ".join(d.name for d in dtos[:5])
            spoken = f"You have {len(dtos)} active medicine schedules: {names}."

        return (
            HealthSummaryResponseData(
                action="list_medicines",
                medicines=dtos,
                disclaimer=HEALTH_DISCLAIMER,
            ),
            spoken,
        )
