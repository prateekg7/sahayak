"""Service orchestrating household chores and fair assignment rotation (T9.3)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.home.adapters.chores import SQLAlchemyChoreRepository
from sahayak.modules.home.adapters.households import SQLAlchemyHouseholdRepository
from sahayak.modules.home.domain.chores import (
    compute_next_chore_turn,
    compute_next_due_date,
    format_chore_added_spoken,
    format_chore_completed_spoken,
    format_chores_list_spoken,
    format_whose_turn_spoken,
    normalize_chore_title,
    normalize_frequency,
)


class ChoreService:
    """Service handling household chore lifecycle, rotation, and completion."""

    def __init__(self, session_factory: Any) -> None:
        self.session_factory = session_factory

    async def _resolve_household_id(
        self,
        *,
        user_id: uuid.UUID,
        household_id_str: str | None,
        uow: UnitOfWork,
    ) -> uuid.UUID:
        """Resolve target household ID or auto-create default 'Family' household."""
        h_repo = SQLAlchemyHouseholdRepository(uow.session)

        if household_id_str and household_id_str.strip():
            try:
                h_id = uuid.UUID(household_id_str.strip())
            except ValueError as err:
                raise InvalidInputError("Invalid household ID format.") from err

            membership = await h_repo.get_membership(household_id=h_id, user_id=user_id)
            if not membership:
                raise NotFoundError(
                    spoken="You do not have access to that household.",
                    detail=f"User {user_id} is not a member of {h_id}",
                )
            return h_id

        households = await h_repo.list_user_households(user_id=user_id)
        if not households:
            new_h, _ = await h_repo.create_household(name="Family", created_by=user_id)
            return new_h.id
        return households[0][0].id

    async def add_chore(
        self,
        *,
        user_id: uuid.UUID,
        household_id_str: str | None = None,
        title: str,
        frequency: str | None = "weekly",
        assigned_to: str | None = None,
        rotation_members: list[str] | None = None,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Add a new recurring household chore with optional rotation."""
        if not title or not title.strip():
            raise InvalidInputError("Please specify a chore title.")

        clean_title = normalize_chore_title(title)
        clean_freq = normalize_frequency(frequency)

        # Parse assigned user ID if provided
        assigned_uuid: uuid.UUID | None = None
        assigned_name = assigned_to
        if assigned_to:
            try:
                assigned_uuid = uuid.UUID(assigned_to.strip())
            except ValueError:
                assigned_uuid = None

        members_list = [m.strip() for m in (rotation_members or []) if m and m.strip()]
        if assigned_to and not members_list:
            members_list = [assigned_to.strip()]

        now = datetime.now(UTC)
        next_due = compute_next_due_date(clean_freq, now)

        async with UnitOfWork(self.session_factory) as uow:
            h_id = await self._resolve_household_id(
                user_id=user_id,
                household_id_str=household_id_str,
                uow=uow,
            )
            chore_repo = SQLAlchemyChoreRepository(uow.session)
            chore = await chore_repo.create_chore(
                household_id=h_id,
                title=clean_title,
                frequency=clean_freq,
                rotation_members=members_list,
                assigned_to=assigned_uuid,
                next_due_at=next_due,
            )
            chore_dict = chore.to_dict()
            await uow.session.commit()

        spoken = format_chore_added_spoken(clean_title, assigned_name, clean_freq)
        data = {
            "household_id": str(h_id),
            "chore": chore_dict,
        }
        next_actions = [
            f"chores(action='whose_turn', title='{clean_title}')",
            f"chores(action='complete', title='{clean_title}')",
        ]
        return data, spoken, next_actions

    async def whose_turn(
        self,
        *,
        user_id: uuid.UUID,
        household_id_str: str | None = None,
        title: str | None = None,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Query who is assigned or whose turn it is for a chore."""
        async with UnitOfWork(self.session_factory) as uow:
            h_id = await self._resolve_household_id(
                user_id=user_id,
                household_id_str=household_id_str,
                uow=uow,
            )
            chore_repo = SQLAlchemyChoreRepository(uow.session)

            if title and title.strip():
                clean_title = normalize_chore_title(title)
                chore = await chore_repo.find_chore_by_title(household_id=h_id, title=clean_title)
                if not chore:
                    raise NotFoundError(
                        spoken=f"Could not find chore '{clean_title}' in your household.",
                        detail=f"Chore '{clean_title}' not found in household {h_id}",
                    )
                chore_dict = chore.to_dict()
                assigned = (
                    str(chore.assigned_to)
                    if chore.assigned_to
                    else (
                        chore.rotation_members[chore.rotation_index % len(chore.rotation_members)]
                        if chore.rotation_members
                        else None
                    )
                )
                spoken = format_whose_turn_spoken(chore.title, assigned, chore.next_due_at)
                data: dict[str, Any] = {
                    "household_id": str(h_id),
                    "chore": chore_dict,
                    "whose_turn": assigned,
                }
                next_actions = [f"chores(action='complete', title='{chore.title}')"]
                return data, spoken, next_actions

            # If no title given, return all chores summary
            chores = await chore_repo.list_chores(household_id=h_id)
            chores_dicts = [c.to_dict() for c in chores]

        spoken = format_chores_list_spoken(chores_dicts)
        summary_data: dict[str, Any] = {
            "household_id": str(h_id),
            "chores": chores_dicts,
            "total_chores": len(chores_dicts),
        }
        next_actions = ["chores(action='add', title='...')"]
        return summary_data, spoken, next_actions

    async def complete_chore(
        self,
        *,
        user_id: uuid.UUID,
        household_id_str: str | None = None,
        title: str,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Mark a chore as complete and advance the rotation."""
        if not title or not title.strip():
            raise InvalidInputError("Please specify which chore you completed.")

        clean_title = normalize_chore_title(title)
        now = datetime.now(UTC)

        async with UnitOfWork(self.session_factory) as uow:
            h_id = await self._resolve_household_id(
                user_id=user_id,
                household_id_str=household_id_str,
                uow=uow,
            )
            chore_repo = SQLAlchemyChoreRepository(uow.session)
            chore = await chore_repo.find_chore_by_title(household_id=h_id, title=clean_title)
            if not chore:
                raise NotFoundError(
                    spoken=f"Could not find chore '{clean_title}'.",
                    detail=f"Chore '{clean_title}' not found in household {h_id}",
                )

            # Calculate next rotation
            next_person, next_idx = compute_next_chore_turn(
                chore.rotation_members,
                chore.rotation_index,
            )
            next_uuid: uuid.UUID | None = None
            if next_person:
                try:
                    next_uuid = uuid.UUID(next_person)
                except ValueError:
                    next_uuid = None

            next_due = compute_next_due_date(chore.frequency, now)

            updated = await chore_repo.complete_chore(
                chore_id=chore.id,
                completed_by=user_id,
                completed_at=now,
                next_assigned_to=next_uuid,
                next_rotation_index=next_idx,
                next_due_at=next_due,
            )
            chore_dict = updated.to_dict() if updated else chore.to_dict()
            await uow.session.commit()

        spoken = format_chore_completed_spoken(clean_title, next_person)
        data = {
            "household_id": str(h_id),
            "chore": chore_dict,
            "next_assigned": next_person,
        }
        next_actions = [f"chores(action='whose_turn', title='{clean_title}')"]
        return data, spoken, next_actions

    async def assign_chore(
        self,
        *,
        user_id: uuid.UUID,
        household_id_str: str | None = None,
        title: str,
        assigned_to: str | None = None,
        rotation_members: list[str] | None = None,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Assign or reassign a chore to a person or set up rotation members."""
        if not title or not title.strip():
            raise InvalidInputError("Please specify a chore title.")

        clean_title = normalize_chore_title(title)
        assigned_uuid: uuid.UUID | None = None
        if assigned_to:
            try:
                assigned_uuid = uuid.UUID(assigned_to.strip())
            except ValueError:
                assigned_uuid = None

        async with UnitOfWork(self.session_factory) as uow:
            h_id = await self._resolve_household_id(
                user_id=user_id,
                household_id_str=household_id_str,
                uow=uow,
            )
            chore_repo = SQLAlchemyChoreRepository(uow.session)
            chore = await chore_repo.find_chore_by_title(household_id=h_id, title=clean_title)
            if not chore:
                raise NotFoundError(
                    spoken=f"Could not find chore '{clean_title}'.",
                    detail=f"Chore '{clean_title}' not found in household {h_id}",
                )

            updated = await chore_repo.update_assignment(
                chore_id=chore.id,
                assigned_to=assigned_uuid,
                rotation_members=rotation_members,
            )
            chore_dict = updated.to_dict() if updated else chore.to_dict()
            await uow.session.commit()

        target_name = assigned_to or (", ".join(rotation_members) if rotation_members else "open")
        spoken = f"Assigned {clean_title} to {target_name}."
        data = {
            "household_id": str(h_id),
            "chore": chore_dict,
        }
        next_actions = [f"chores(action='whose_turn', title='{clean_title}')"]
        return data, spoken, next_actions

    async def list_chores(
        self,
        *,
        user_id: uuid.UUID,
        household_id_str: str | None = None,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """List all chores for the household."""
        return await self.whose_turn(
            user_id=user_id,
            household_id_str=household_id_str,
            title=None,
        )
