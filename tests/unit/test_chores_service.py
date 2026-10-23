"""Unit and integration tests for ChoreService (T9.3)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import NotFoundError
from sahayak.modules.home.service.chores import ChoreService
from sahayak.shared.users.models import User


@pytest.mark.asyncio
async def test_chore_service_lifecycle_and_rotation() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    service = ChoreService(session_factory=session_factory)
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_a))
            uow.session.add(User(id=user_b))
            await uow.session.commit()

        # 1. Add chore (auto-creates default Family household)
        data_add, spoken_add, _ = await service.add_chore(
            user_id=user_a,
            title="Clean Kitchen Counters",
            frequency="daily",
        )
        assert data_add["chore"]["title"] == "Clean Kitchen Counters"
        assert data_add["chore"]["frequency"] == "daily"
        assert "Clean Kitchen Counters" in spoken_add
        household_id = data_add["household_id"]

        # 2. Assign rotation members (e.g. Alice and Bob)
        data_assign, spoken_assign, _ = await service.assign_chore(
            user_id=user_a,
            household_id_str=household_id,
            title="Clean Kitchen Counters",
            rotation_members=["Alice", "Bob"],
        )
        assert data_assign["chore"]["rotation_members"] == ["Alice", "Bob"]
        assert data_assign["chore"]["rotation_index"] == 0
        assert "Alice" in spoken_assign

        # 3. Check whose turn
        data_turn, spoken_turn, _ = await service.whose_turn(
            user_id=user_a,
            household_id_str=household_id,
            title="Clean Kitchen Counters",
        )
        assert data_turn["whose_turn"] == "Alice"
        assert "Alice" in spoken_turn

        # 4. Complete chore -> rotates to Bob
        data_comp, spoken_comp, _ = await service.complete_chore(
            user_id=user_a,
            household_id_str=household_id,
            title="Clean Kitchen Counters",
        )
        assert data_comp["chore"]["rotation_index"] == 1
        assert "Bob" in spoken_comp

        # 5. List chores
        data_list, spoken_list, _ = await service.list_chores(
            user_id=user_a,
            household_id_str=household_id,
        )
        assert len(data_list["chores"]) >= 1
        assert "Clean Kitchen Counters" in spoken_list

        # 6. User B cannot access User A's household chores
        with pytest.raises(NotFoundError):
            await service.list_chores(
                user_id=user_b,
                household_id_str=household_id,
            )

    finally:
        await engine.dispose()
