"""Unit and integration tests for PantryService (T9.3)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import NotFoundError
from sahayak.modules.home.service.lists import SharedListService
from sahayak.modules.home.service.pantry import PantryService
from sahayak.shared.users.models import User


@pytest.mark.asyncio
async def test_pantry_service_lifecycle_and_shopping_handoff() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    list_service = SharedListService(session_factory=session_factory)
    pantry_service = PantryService(session_factory=session_factory, list_service=list_service)
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_a))
            uow.session.add(User(id=user_b))
            await uow.session.commit()

        # 1. Add pantry item (auto-creates default Family household)
        data_add, spoken_add, _ = await pantry_service.add_item(
            user_id=user_a,
            item="500 g pasta",
            expires_in_days=30,
        )
        assert data_add["item"]["item_name"] == "Pasta"
        assert data_add["item"]["quantity"] == "500 g"
        assert "Pasta" in spoken_add
        household_id = data_add["household_id"]

        # 2. Add olive oil
        await pantry_service.add_item(
            user_id=user_a,
            household_id_str=household_id,
            item="Extra Virgin Olive Oil",
            quantity="500 ml",
        )

        # 3. List pantry items
        data_list, spoken_list, _ = await pantry_service.list_items(
            user_id=user_a,
            household_id_str=household_id,
        )
        assert len(data_list["items"]) >= 2
        assert "pantry" in spoken_list.lower()

        # 4. Set preferences
        data_pref, spoken_pref, _ = await pantry_service.set_preferences(
            user_id=user_a,
            household_id_str=household_id,
            diet="vegetarian",
            allergies=["peanuts"],
        )
        assert data_pref["preferences"]["diet"] == "vegetarian"
        assert data_pref["preferences"]["allergies"] == ["peanuts"]
        assert "preferences" in spoken_pref.lower()

        # 5. Suggest recipes with add_missing_to_shopping_list=True
        data_rec, spoken_rec, _ = await pantry_service.suggest_recipes(
            user_id=user_a,
            household_id_str=household_id,
            add_missing_to_shopping_list=True,
        )
        assert len(data_rec["recipes"]) >= 1
        assert len(spoken_rec) <= 300

        # Verify missing ingredients were added to shopping list!
        data_shopping, _, _ = await list_service.read_list(
            user_id=user_a,
            household_id_str=household_id,
            list_name="shopping",
        )
        assert len(data_shopping["items"]) >= 1

        # 6. Generate meal plan
        data_plan, spoken_plan, _ = await pantry_service.meal_plan(
            user_id=user_a,
            household_id_str=household_id,
            days=3,
        )
        assert len(data_plan["plan"]) == 3
        assert len(spoken_plan) <= 300

        # 7. User B cross-household access denied
        with pytest.raises(NotFoundError):
            await pantry_service.list_items(
                user_id=user_b,
                household_id_str=household_id,
            )

    finally:
        await engine.dispose()
