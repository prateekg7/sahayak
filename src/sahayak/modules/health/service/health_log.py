"""Application service orchestrating personal health logging workflows (T7.1)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.health.adapters.entries import SQLAlchemyHealthRepository
from sahayak.modules.health.domain.entries import (
    HEALTH_DISCLAIMER,
    format_health_list_spoken,
    format_health_logged_spoken,
    format_health_undo_spoken,
    normalize_health_kind,
    validate_meal_entry,
    validate_sleep_entry,
    validate_water_entry,
    validate_weight_entry,
    validate_workout_entry,
)
from sahayak.modules.health.models import HealthEntry
from sahayak.modules.health.schemas import (
    HealthEntryData,
    HealthLogRequest,
    HealthLogResponseData,
)


class HealthLogService:
    """Service managing personal health logging, history listing, and undos."""

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

    def _entry_to_data(self, entry: HealthEntry) -> HealthEntryData:
        return HealthEntryData(
            id=str(entry.id),
            user_id=str(entry.user_id),
            kind=entry.kind,
            data=entry.data,
            occurred_at=entry.occurred_at.isoformat() if entry.occurred_at else None,
        )

    async def execute(
        self,
        user_id: uuid.UUID,
        request: HealthLogRequest,
    ) -> tuple[HealthLogResponseData, str]:
        """Dispatch health log action and return response payload and spoken summary."""
        action = request.action.value if hasattr(request.action, "value") else str(request.action)

        if action == "log":
            return await self._handle_log(user_id, request)
        if action == "list":
            return await self._handle_list(user_id, request)
        if action == "undo_last":
            return await self._handle_undo(user_id, request)
        if action == "delete":
            return await self._handle_delete(user_id, request)

        raise InvalidInputError(
            f"Unknown action: {action}. Expected 'log', 'list', 'undo_last', or 'delete'."
        )

    async def _handle_log(
        self,
        user_id: uuid.UUID,
        request: HealthLogRequest,
    ) -> tuple[HealthLogResponseData, str]:
        kind = normalize_health_kind(request.kind)

        if kind == "water":
            entry_data = validate_water_entry(request.value, request.unit)
        elif kind == "weight":
            entry_data = validate_weight_entry(request.value, request.unit)
        elif kind == "sleep":
            entry_data = validate_sleep_entry(request.value, request.unit)
        elif kind == "workout":
            entry_data = validate_workout_entry(
                activity=request.activity,
                duration=request.duration or request.value,
                unit=request.unit,
                intensity=request.intensity,
            )
        elif kind == "meal":
            entry_data = validate_meal_entry(
                meal_name=request.meal_name or (str(request.value) if request.value else None),
                meal_type=request.meal_type,
                calories=request.calories,
                notes=request.notes,
            )
        else:
            raise InvalidInputError(f"Unsupported kind '{kind}'.")

        now = self._now()
        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyHealthRepository(uow.session)
            entry = await repo.create_entry(
                user_id=user_id,
                kind=kind,
                data=entry_data,
                occurred_at=now,
            )

        spoken = format_health_logged_spoken(kind, entry.data)
        entry_dto = self._entry_to_data(entry)

        return (
            HealthLogResponseData(
                action="log",
                kind=kind,
                entry=entry_dto,
                entries=[entry_dto],
                count=1,
                disclaimer=HEALTH_DISCLAIMER,
            ),
            spoken,
        )

    async def _handle_list(
        self,
        user_id: uuid.UUID,
        request: HealthLogRequest,
    ) -> tuple[HealthLogResponseData, str]:
        kind = request.kind.strip().lower() if request.kind else None
        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyHealthRepository(uow.session)
            entries = await repo.list_entries(
                user_id=user_id,
                kind=kind,
                limit=request.limit,
            )

        dtos = [self._entry_to_data(e) for e in entries]
        spoken = format_health_list_spoken(kind, [d.model_dump() for d in dtos])

        return (
            HealthLogResponseData(
                action="list",
                kind=kind,
                entries=dtos,
                count=len(dtos),
                disclaimer=HEALTH_DISCLAIMER,
            ),
            spoken,
        )

    async def _handle_undo(
        self,
        user_id: uuid.UUID,
        request: HealthLogRequest,
    ) -> tuple[HealthLogResponseData, str]:
        kind = request.kind.strip().lower() if request.kind else None
        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyHealthRepository(uow.session)
            entry = await repo.undo_last_entry(user_id=user_id, kind=kind)

        if entry is None:
            kind_str = f" for {kind}" if kind else ""
            spoken = f"You have no recent health entries{kind_str} to undo."
            return (
                HealthLogResponseData(
                    action="undo_last",
                    kind=kind,
                    entry=None,
                    count=0,
                    disclaimer=HEALTH_DISCLAIMER,
                ),
                spoken,
            )

        spoken = format_health_undo_spoken(entry.kind, entry.data)
        entry_dto = self._entry_to_data(entry)
        return (
            HealthLogResponseData(
                action="undo_last",
                kind=entry.kind,
                entry=entry_dto,
                entries=[entry_dto],
                count=1,
                disclaimer=HEALTH_DISCLAIMER,
            ),
            spoken,
        )

    async def _handle_delete(
        self,
        user_id: uuid.UUID,
        request: HealthLogRequest,
    ) -> tuple[HealthLogResponseData, str]:
        if not request.entry_id:
            raise InvalidInputError("Entry ID is required to delete a health entry.")
        try:
            entry_uuid = uuid.UUID(request.entry_id)
        except ValueError as err:
            raise InvalidInputError(f"Invalid entry ID: {request.entry_id}") from err

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyHealthRepository(uow.session)
            deleted = await repo.delete_entry(user_id=user_id, entry_id=entry_uuid)

        if not deleted:
            raise NotFoundError(f"Health entry {request.entry_id} not found.")

        spoken = "Deleted the requested health entry."
        return (
            HealthLogResponseData(
                action="delete",
                kind=request.kind,
                entry=None,
                count=1,
                disclaimer=HEALTH_DISCLAIMER,
            ),
            spoken,
        )
