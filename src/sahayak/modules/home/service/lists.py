"""SharedListService handling family lists, item merging, and speech formatting (T9.2)."""

from __future__ import annotations

import uuid
from typing import Any

from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.home.adapters.households import SQLAlchemyHouseholdRepository
from sahayak.modules.home.adapters.lists import SQLAlchemyListRepository
from sahayak.modules.home.domain.lists import (
    format_added_spoken,
    format_checked_off_spoken,
    format_cleared_spoken,
    format_list_items_spoken,
    format_removed_spoken,
    normalize_list_name,
    parse_item_and_quantity,
)


class SharedListService:
    """Service orchestrating shared list operations within verified households."""

    def __init__(self, session_factory: Any) -> None:
        self.session_factory = session_factory

    async def _resolve_household_id(
        self,
        *,
        user_id: uuid.UUID,
        household_id_str: str | None,
        uow: UnitOfWork,
    ) -> uuid.UUID:
        """Resolve target household ID or fallback to user's primary household."""
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

        # Fallback to user's first household, or auto-create default Family household
        households = await h_repo.list_user_households(user_id=user_id)
        if not households:
            new_h, _ = await h_repo.create_household(name="Family", created_by=user_id)
            return new_h.id
        return households[0][0].id

    async def add_item(
        self,
        *,
        user_id: uuid.UUID,
        household_id_str: str | None = None,
        list_name: str | None = "shopping",
        item: str,
        quantity: str | None = None,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Add or update an item on a shared list."""
        if not item or not item.strip():
            raise InvalidInputError("Please specify an item to add to the list.")

        parsed_item, parsed_qty = parse_item_and_quantity(item, quantity)
        clean_list_name = normalize_list_name(list_name)

        async with UnitOfWork(self.session_factory) as uow:
            h_id = await self._resolve_household_id(
                user_id=user_id,
                household_id_str=household_id_str,
                uow=uow,
            )
            list_repo = SQLAlchemyListRepository(uow.session)
            s_list = await list_repo.get_or_create_list(
                household_id=h_id,
                name=clean_list_name,
            )
            list_item = await list_repo.add_or_update_item(
                list_id=s_list.id,
                item_name=parsed_item,
                quantity=parsed_qty,
                added_by=user_id,
            )
            list_dict = s_list.to_dict()
            item_dict = list_item.to_dict()
            await uow.session.commit()

        spoken = format_added_spoken(parsed_item, parsed_qty, clean_list_name)
        data = {
            "household_id": str(h_id),
            "list": list_dict,
            "item": item_dict,
        }
        next_actions = [
            f"shared_list(action='read', list_name='{clean_list_name}', household_id='{h_id}')",
            f"shared_list(action='check_off', item='{parsed_item}', list_name='{clean_list_name}')",
        ]
        return data, spoken, next_actions

    async def read_list(
        self,
        *,
        user_id: uuid.UUID,
        household_id_str: str | None = None,
        list_name: str | None = "shopping",
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Read all items on a shared list."""
        clean_list_name = normalize_list_name(list_name)

        async with UnitOfWork(self.session_factory) as uow:
            h_id = await self._resolve_household_id(
                user_id=user_id,
                household_id_str=household_id_str,
                uow=uow,
            )
            list_repo = SQLAlchemyListRepository(uow.session)
            s_list = await list_repo.get_list_by_name(
                household_id=h_id,
                name=clean_list_name,
            )
            if not s_list:
                items_dicts: list[dict[str, Any]] = []
                list_dict = {"name": clean_list_name, "household_id": str(h_id)}
            else:
                items = await list_repo.get_list_items(list_id=s_list.id, include_checked=True)
                items_dicts = [it.to_dict() for it in items]
                list_dict = s_list.to_dict()

        spoken = format_list_items_spoken(clean_list_name, items_dicts)
        data = {
            "household_id": str(h_id),
            "list": list_dict,
            "items": items_dicts,
            "total_items": len(items_dicts),
        }
        next_actions = [
            f"shared_list(action='add', item='...', list_name='{clean_list_name}')",
            f"shared_list(action='clear_checked', list_name='{clean_list_name}')",
        ]
        return data, spoken, next_actions

    async def check_off_item(
        self,
        *,
        user_id: uuid.UUID,
        household_id_str: str | None = None,
        list_name: str | None = "shopping",
        item: str,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Check off an item from a shared list."""
        if not item or not item.strip():
            raise InvalidInputError("Please specify which item to check off.")

        clean_item = item.strip()
        clean_list_name = normalize_list_name(list_name)

        async with UnitOfWork(self.session_factory) as uow:
            h_id = await self._resolve_household_id(
                user_id=user_id,
                household_id_str=household_id_str,
                uow=uow,
            )
            list_repo = SQLAlchemyListRepository(uow.session)
            s_list = await list_repo.get_list_by_name(
                household_id=h_id,
                name=clean_list_name,
            )
            if not s_list:
                raise NotFoundError(
                    spoken=f"Your {clean_list_name.replace('-', ' ')} list is empty.",
                    detail=f"List '{clean_list_name}' not found for household {h_id}",
                )

            found_item = await list_repo.find_item_by_name(
                list_id=s_list.id,
                item_name=clean_item,
            )
            if not found_item:
                display_list = clean_list_name.replace("-", " ")
                raise NotFoundError(
                    spoken=f"Could not find {clean_item} on your {display_list} list.",
                    detail=f"Item '{clean_item}' not found on list {s_list.id}",
                )

            updated = await list_repo.check_off_item(item_id=found_item.id)
            list_dict = s_list.to_dict()
            item_dict = updated.to_dict() if updated else found_item.to_dict()
            await uow.session.commit()

        spoken = format_checked_off_spoken(clean_item, clean_list_name)
        data = {
            "household_id": str(h_id),
            "list": list_dict,
            "item": item_dict,
        }
        next_actions = [
            f"shared_list(action='read', list_name='{clean_list_name}')",
            f"shared_list(action='clear_checked', list_name='{clean_list_name}')",
        ]
        return data, spoken, next_actions

    async def remove_item(
        self,
        *,
        user_id: uuid.UUID,
        household_id_str: str | None = None,
        list_name: str | None = "shopping",
        item: str,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Remove an item from a shared list."""
        if not item or not item.strip():
            raise InvalidInputError("Please specify which item to remove.")

        clean_item = item.strip()
        clean_list_name = normalize_list_name(list_name)

        async with UnitOfWork(self.session_factory) as uow:
            h_id = await self._resolve_household_id(
                user_id=user_id,
                household_id_str=household_id_str,
                uow=uow,
            )
            list_repo = SQLAlchemyListRepository(uow.session)
            s_list = await list_repo.get_list_by_name(
                household_id=h_id,
                name=clean_list_name,
            )
            if not s_list:
                raise NotFoundError(
                    spoken=f"Your {clean_list_name.replace('-', ' ')} list is empty.",
                    detail=f"List '{clean_list_name}' not found for household {h_id}",
                )

            found_item = await list_repo.find_item_by_name(
                list_id=s_list.id,
                item_name=clean_item,
            )
            if not found_item:
                display_list = clean_list_name.replace("-", " ")
                raise NotFoundError(
                    spoken=f"Could not find {clean_item} on your {display_list} list.",
                    detail=f"Item '{clean_item}' not found on list {s_list.id}",
                )

            list_dict = s_list.to_dict()
            await list_repo.remove_item(item_id=found_item.id)
            await uow.session.commit()

        spoken = format_removed_spoken(clean_item, clean_list_name)
        data = {
            "household_id": str(h_id),
            "list": list_dict,
            "removed_item": clean_item,
        }
        next_actions = [
            f"shared_list(action='read', list_name='{clean_list_name}')",
        ]
        return data, spoken, next_actions

    async def clear_checked(
        self,
        *,
        user_id: uuid.UUID,
        household_id_str: str | None = None,
        list_name: str | None = "shopping",
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Remove all checked off items from a list."""
        clean_list_name = normalize_list_name(list_name)

        async with UnitOfWork(self.session_factory) as uow:
            h_id = await self._resolve_household_id(
                user_id=user_id,
                household_id_str=household_id_str,
                uow=uow,
            )
            list_repo = SQLAlchemyListRepository(uow.session)
            s_list = await list_repo.get_list_by_name(
                household_id=h_id,
                name=clean_list_name,
            )
            count = 0
            if s_list:
                count = await list_repo.clear_checked_items(list_id=s_list.id)
                await uow.session.commit()

        spoken = format_cleared_spoken(count, clean_list_name)
        data = {
            "household_id": str(h_id),
            "cleared_count": count,
            "list_name": clean_list_name,
        }
        next_actions = [
            f"shared_list(action='read', list_name='{clean_list_name}')",
        ]
        return data, spoken, next_actions
