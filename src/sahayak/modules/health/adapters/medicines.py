"""SQLAlchemy repository adapter for medicine schedules and doses (T7.2)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sahayak.modules.health.models import Medicine, MedicineDose
from sahayak.modules.health.ports import MedicineRepositoryPort


class SQLAlchemyMedicineRepository(MedicineRepositoryPort):
    """SQLAlchemy implementation of MedicineRepositoryPort."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_medicine(
        self,
        user_id: uuid.UUID,
        name: str,
        dosage_text: str,
        times: list[str],
        days: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> Medicine:
        """Create and persist a new medicine schedule."""
        clean_name = name.strip()
        med = Medicine(
            user_id=user_id,
            name=clean_name,
            dosage_text=dosage_text.strip() if dosage_text else "1 dose",
            times=times,
            days=days,
            start_date=start_date or date.today(),
            end_date=end_date,
            is_active=True,
        )
        self.session.add(med)
        await self.session.flush()
        return med

    async def get_medicine(
        self,
        user_id: uuid.UUID,
        medicine_id: uuid.UUID,
    ) -> Medicine | None:
        """Retrieve a medicine schedule by ID scoped by user_id."""
        stmt = select(Medicine).where(
            Medicine.id == medicine_id,
            Medicine.user_id == user_id,
        )
        res = await self.session.execute(stmt)
        return res.scalars().first()

    async def find_medicine_by_name(
        self,
        user_id: uuid.UUID,
        name: str,
    ) -> Medicine | None:
        """Find an active medicine matching the name."""
        clean = name.strip().lower()
        stmt = select(Medicine).where(
            Medicine.user_id == user_id,
            Medicine.is_active.is_(True),
            Medicine.name.ilike(f"%{clean}%"),
        )
        res = await self.session.execute(stmt)
        return res.scalars().first()

    async def list_medicines(
        self,
        user_id: uuid.UUID,
        is_active: bool = True,
    ) -> list[Medicine]:
        """List medicine schedules for a user."""
        stmt = (
            select(Medicine)
            .where(
                Medicine.user_id == user_id,
                Medicine.is_active == is_active,
            )
            .order_by(Medicine.name.asc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def record_or_update_dose(
        self,
        user_id: uuid.UUID,
        medicine_id: uuid.UUID,
        scheduled_date: date,
        scheduled_time: str,
        status: str = "taken",
        taken_at: datetime | None = None,
    ) -> MedicineDose:
        """Record or update a medicine dose status."""
        stmt = select(MedicineDose).where(
            MedicineDose.medicine_id == medicine_id,
            MedicineDose.scheduled_date == scheduled_date,
            MedicineDose.scheduled_time == scheduled_time,
        )
        res = await self.session.execute(stmt)
        existing = res.scalars().first()

        if existing is not None:
            existing.status = status
            existing.taken_at = taken_at or (datetime.now() if status == "taken" else None)
            await self.session.flush()
            return existing

        dose = MedicineDose(
            medicine_id=medicine_id,
            user_id=user_id,
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time,
            status=status,
            taken_at=taken_at or (datetime.now() if status == "taken" else None),
        )
        self.session.add(dose)
        await self.session.flush()
        return dose

    async def list_doses_for_date(
        self,
        user_id: uuid.UUID,
        scheduled_date: date,
    ) -> list[MedicineDose]:
        """List recorded doses for a specific date."""
        stmt = (
            select(MedicineDose)
            .where(
                MedicineDose.user_id == user_id,
                MedicineDose.scheduled_date == scheduled_date,
            )
            .order_by(MedicineDose.scheduled_time.asc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def list_doses_in_range(
        self,
        user_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> list[MedicineDose]:
        """List recorded doses in a date range."""
        stmt = (
            select(MedicineDose)
            .where(
                MedicineDose.user_id == user_id,
                MedicineDose.scheduled_date >= start_date,
                MedicineDose.scheduled_date <= end_date,
            )
            .order_by(MedicineDose.scheduled_date.asc(), MedicineDose.scheduled_time.asc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def deactivate_medicine(
        self,
        user_id: uuid.UUID,
        medicine_id: uuid.UUID,
    ) -> bool:
        """Deactivate a medicine schedule."""
        med = await self.get_medicine(user_id, medicine_id)
        if med is None:
            return False
        med.is_active = False
        await self.session.flush()
        return True
