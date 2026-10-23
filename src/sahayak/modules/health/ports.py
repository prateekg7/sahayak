"""Port interfaces for the health module (T7.1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Protocol

from sahayak.modules.health.models import HealthEntry


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
