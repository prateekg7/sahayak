"""Port interfaces for the health module (T7.1, T7.2)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Protocol

from sahayak.modules.health.models import HealthEntry, Medicine, MedicineDose


class HealthRepositoryPort(Protocol):
    """Repository port interface for personal health metric entries."""

    async def create_entry(
        self,
        user_id: uuid.UUID,
        kind: str,
        data: dict[str, Any],
        occurred_at: datetime | None = None,
    ) -> HealthEntry:
        """Create and persist a new health entry."""
        ...

    async def get_entry(
        self,
        user_id: uuid.UUID,
        entry_id: uuid.UUID,
    ) -> HealthEntry | None:
        """Retrieve an entry by ID, scoped by user_id."""
        ...

    async def list_entries(
        self,
        user_id: uuid.UUID,
        kind: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 10,
    ) -> list[HealthEntry]:
        """List active entries for a user, ordered by occurred_at DESC."""
        ...

    async def undo_last_entry(
        self,
        user_id: uuid.UUID,
        kind: str | None = None,
    ) -> HealthEntry | None:
        """Undo the most recent active health entry by marking it deleted."""
        ...

    async def delete_entry(
        self,
        user_id: uuid.UUID,
        entry_id: uuid.UUID,
    ) -> bool:
        """Soft delete a specific health entry."""
        ...


class MedicineRepositoryPort(Protocol):
    """Repository port interface for medicine schedule tracking."""

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
        """Create a new medicine schedule."""
        ...

    async def get_medicine(
        self,
        user_id: uuid.UUID,
        medicine_id: uuid.UUID,
    ) -> Medicine | None:
        """Retrieve a medicine schedule by ID."""
        ...

    async def find_medicine_by_name(
        self,
        user_id: uuid.UUID,
        name: str,
    ) -> Medicine | None:
        """Find an active medicine by name (case-insensitive substring/prefix)."""
        ...

    async def list_medicines(
        self,
        user_id: uuid.UUID,
        is_active: bool = True,
    ) -> list[Medicine]:
        """List medicine schedules for a user."""
        ...

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
        ...

    async def list_doses_for_date(
        self,
        user_id: uuid.UUID,
        scheduled_date: date,
    ) -> list[MedicineDose]:
        """List recorded doses for a specific date."""
        ...

    async def list_doses_in_range(
        self,
        user_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> list[MedicineDose]:
        """List recorded doses in a date range."""
        ...

    async def deactivate_medicine(
        self,
        user_id: uuid.UUID,
        medicine_id: uuid.UUID,
    ) -> bool:
        """Deactivate a medicine schedule."""
        ...
