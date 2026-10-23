"""Unit and integration tests for SharedListService (T9.2)."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import NotFoundError
from sahayak.modules.home.service.households import HouseholdService
from sahayak.modules.home.service.lists import SharedListService
from sahayak.shared.users.models import User


@pytest.mark.asyncio
async def test_shared_list_lifecycle_and_deduplication() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    service = SharedListService(session_factory=session_factory)
    user_id = uuid.uuid4()

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.commit()

        # 1. Add item with automatic household creation
        data_add, spoken_add, _ = await service.add_item(
            user_id=user_id,
            list_name="Groceries",
            item="Whole Milk",
            quantity="1 gallon",
        )
        assert "household_id" in data_add
        assert data_add["item"]["item_name"] == "Whole Milk"
        assert data_add["item"]["quantity"] == "1 gallon"
        assert "Whole Milk" in spoken_add
        household_id = data_add["household_id"]

        # 2. Add same item again (case-insensitive deduplication merge)
        data_merge, _, _ = await service.add_item(
            user_id=user_id,
            household_id_str=household_id,
            list_name="Groceries",
            item="whole milk",
            quantity="2 gallons",
        )
        assert data_merge["item"]["quantity"] == "2 gallons"
        assert data_merge["item"]["id"] == data_add["item"]["id"]

        # 3. Add second item
        await service.add_item(
            user_id=user_id,
            household_id_str=household_id,
            list_name="Groceries",
            item="organic eggs",
            quantity="1 dozen",
        )

        # 4. Read list
        data_read, spoken_read, _ = await service.read_list(
            user_id=user_id,
            household_id_str=household_id,
            list_name="Groceries",
        )
        assert data_read["total_items"] == 2
        assert "2 items" in spoken_read

        # 5. Check off item
        data_check, spoken_check, _ = await service.check_off_item(
            user_id=user_id,
            household_id_str=household_id,
            list_name="Groceries",
            item="whole milk",
        )
        assert data_check["item"]["checked"] is True
        assert "Checked off" in spoken_check

        # 6. Clear checked items
        data_clear, spoken_clear, _ = await service.clear_checked(
            user_id=user_id,
            household_id_str=household_id,
            list_name="Groceries",
        )
        assert data_clear["cleared_count"] == 1
        assert "Cleared 1 checked item" in spoken_clear

        # 7. Verify remaining items
        data_remain, _, _ = await service.read_list(
            user_id=user_id,
            household_id_str=household_id,
            list_name="Groceries",
        )
        assert data_remain["total_items"] == 1
        assert data_remain["items"][0]["item_name"] == "Organic Eggs"

        # 8. Remove remaining item
        data_rem, spoken_rem, _ = await service.remove_item(
            user_id=user_id,
            household_id_str=household_id,
            list_name="Groceries",
            item="Organic Eggs",
        )
        assert data_rem["removed_item"] == "Organic Eggs"
        assert "Removed Organic Eggs" in spoken_rem

        # 9. List is now empty
        data_empty, spoken_empty, _ = await service.read_list(
            user_id=user_id,
            household_id_str=household_id,
            list_name="Groceries",
        )
        assert data_empty["total_items"] == 0
        assert "currently empty" in spoken_empty
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_shared_list_authorization_and_cross_household_isolation() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    service = SharedListService(session_factory=session_factory)
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add_all([User(id=user_a), User(id=user_b)])
            await uow.session.commit()

        # User A creates item in their household
        data_a, _, _ = await service.add_item(
            user_id=user_a,
            list_name="Hardware",
            item="Hammer",
        )
        h_a = data_a["household_id"]

        # User B attempting to access User A's household list must be rejected
        with pytest.raises(NotFoundError):
            await service.read_list(
                user_id=user_b,
                household_id_str=h_a,
                list_name="Hardware",
            )

        with pytest.raises(NotFoundError):
            await service.check_off_item(
                user_id=user_b,
                household_id_str=h_a,
                list_name="Hardware",
                item="Hammer",
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_list_modifications() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    service = SharedListService(session_factory=session_factory)
    h_service = HouseholdService(session_factory=session_factory)

    user_owner = uuid.uuid4()
    user_member = uuid.uuid4()

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add_all([User(id=user_owner), User(id=user_member)])
            await uow.session.commit()

        # Create household and join member
        h_data, _, _ = await h_service.create_household(user_id=user_owner, name="Shared Villa")
        invite_code = h_data["invite"]["code"]
        await h_service.join_household(user_id=user_member, invite_code=invite_code)
        h_id = h_data["household"]["id"]

        # Concurrently add items from both users
        tasks = [
            service.add_item(
                user_id=user_owner,
                household_id_str=h_id,
                list_name="Groceries",
                item=f"Owner Item {i}",
            )
            for i in range(5)
        ] + [
            service.add_item(
                user_id=user_member,
                household_id_str=h_id,
                list_name="Groceries",
                item=f"Member Item {i}",
            )
            for i in range(5)
        ]

        results = await asyncio.gather(*tasks)
        assert len(results) == 10

        # Verify all 10 items exist on list
        read_data, _, _ = await service.read_list(
            user_id=user_owner,
            household_id_str=h_id,
            list_name="Groceries",
        )
        assert read_data["total_items"] == 10
    finally:
        await engine.dispose()
