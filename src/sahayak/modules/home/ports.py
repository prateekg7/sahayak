"""Repository and adapter ports for the home and family module (T9.1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol

from sahayak.modules.home.models import (
    Household,
    HouseholdInvite,
    HouseholdMembership,
    SharedList,
    SharedListItem,
)


class HouseholdRepositoryPort(Protocol):
    """Port defining household, membership, and invite persistence operations."""

    async def create_household(
        self,
        *,
        created_by: uuid.UUID,
        name: str,
    ) -> tuple[Household, HouseholdMembership]:
        """Create a new household and assign creator as owner."""
        ...

    async def get_household(
        self,
        *,
        household_id: uuid.UUID,
    ) -> Household | None:
        """Fetch household by ID."""
        ...

    async def get_membership(
        self,
        *,
        household_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> HouseholdMembership | None:
        """Fetch specific user membership in a household."""
        ...

    async def list_user_households(
        self,
        *,
        user_id: uuid.UUID,
    ) -> list[tuple[Household, HouseholdMembership]]:
        """List all households where the user is an active member."""
        ...

    async def create_invite(
        self,
        *,
        household_id: uuid.UUID,
        created_by: uuid.UUID,
        code: str,
        expires_at: datetime,
    ) -> HouseholdInvite:
        """Create a new expiring invite code."""
        ...

    async def get_active_invite(
        self,
        *,
        code: str,
        now: datetime,
    ) -> HouseholdInvite | None:
        """Lookup an unused, unexpired invite code."""
        ...

    async def mark_invite_used(
        self,
        *,
        invite_id: uuid.UUID,
        used_by: uuid.UUID,
        now: datetime,
    ) -> None:
        """Mark an invite code as used."""
        ...

    async def add_member(
        self,
        *,
        household_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str = "member",
    ) -> HouseholdMembership:
        """Add user as member or owner of household."""
        ...

    async def list_members(
        self,
        *,
        household_id: uuid.UUID,
    ) -> list[HouseholdMembership]:
        """List all members of a household."""
        ...

    async def remove_member(
        self,
        *,
        household_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Remove a user membership from a household."""
        ...

    async def delete_household(
        self,
        *,
        household_id: uuid.UUID,
    ) -> bool:
        """Delete household and all its cascade children."""
        ...


class ListRepositoryPort(Protocol):
    """Port defining shared list and list items operations."""

    async def get_or_create_list(
        self,
        *,
        household_id: uuid.UUID,
        name: str,
    ) -> SharedList:
        """Fetch existing list by name or create a new one."""
        ...

    async def get_list_by_name(
        self,
        *,
        household_id: uuid.UUID,
        name: str,
    ) -> SharedList | None:
        """Fetch list by household and name."""
        ...

    async def add_or_update_item(
        self,
        *,
        list_id: uuid.UUID,
        item_name: str,
        quantity: str | None,
        added_by: uuid.UUID | None,
    ) -> SharedListItem:
        """Add new item or update quantity of existing unchecked item."""
        ...

    async def get_list_items(
        self,
        *,
        list_id: uuid.UUID,
        include_checked: bool = True,
    ) -> list[SharedListItem]:
        """Fetch items on a list ordered by created_at."""
        ...

    async def find_item_by_name(
        self,
        *,
        list_id: uuid.UUID,
        item_name: str,
    ) -> SharedListItem | None:
        """Find item by case-insensitive name."""
        ...

    async def check_off_item(
        self,
        *,
        item_id: uuid.UUID,
    ) -> SharedListItem | None:
        """Mark an item as checked."""
        ...

    async def remove_item(
        self,
        *,
        item_id: uuid.UUID,
    ) -> bool:
        """Remove an item from a list."""
        ...

    async def clear_checked_items(
        self,
        *,
        list_id: uuid.UUID,
    ) -> int:
        """Delete all checked items from a list, returning count deleted."""
        ...
