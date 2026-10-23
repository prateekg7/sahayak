"""Unit and concurrency tests for OrderService (T10.1)."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.business.service.orders import OrderService
from sahayak.shared.users.models import User


@pytest.mark.asyncio
async def test_order_service_lifecycle_and_transitions() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    service = OrderService(session_factory=session_factory)
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_a))
            uow.session.add(User(id=user_b))
            await uow.session.commit()

        # 1. Create order
        data_create, spoken_create, _ = await service.create_order(
            user_id=user_a,
            customer_name="Ramesh Sharma",
            items=[
                {"item_name": "Premium Notebook", "quantity": 2, "unit_price_minor": 7500},
                {"item_name": "Gel Pen", "quantity": 3, "unit_price_minor": 1000},
            ],
            notes="Handle with care",
        )
        assert data_create["order"]["order_number"] == 1
        assert data_create["order"]["total_amount_minor"] == 18000
        assert data_create["order"]["status"] == "pending"
        assert len(data_create["items"]) == 2
        assert "180 rupees" in spoken_create
        business_id = data_create["business_id"]

        # 2. List pending
        data_pending, spoken_pending, _ = await service.list_pending(
            user_id=user_a,
            business_id_str=business_id,
        )
        assert len(data_pending["orders"]) == 1
        assert data_pending["orders"][0]["order_number"] == 1
        assert "order 1 for Ramesh Sharma is pending" in spoken_pending

        # 3. Get order details
        data_get, spoken_get, _ = await service.get_order(
            user_id=user_a,
            business_id_str=business_id,
            order_number=1,
        )
        assert data_get["order"]["customer_name"] == "Ramesh Sharma"
        assert "Premium Notebook" in spoken_get

        # 4. Valid status transitions: pending -> packed -> shipped
        data_pack, spoken_pack, _ = await service.update_status(
            user_id=user_a,
            business_id_str=business_id,
            order_number=1,
            new_status="packed",
        )
        assert data_pack["order"]["status"] == "packed"
        assert "Marked order 1 as packed." in spoken_pack

        data_ship, spoken_ship, _ = await service.update_status(
            user_id=user_a,
            business_id_str=business_id,
            order_number=1,
            new_status="shipped",
        )
        assert data_ship["order"]["status"] == "shipped"

        # 5. Illegal transition: shipped -> pending
        with pytest.raises(InvalidInputError, match="directly to pending"):
            await service.update_status(
                user_id=user_a,
                business_id_str=business_id,
                order_number=1,
                new_status="pending",
            )

        # 6. User B cross-business access denied
        with pytest.raises(NotFoundError):
            await service.get_order(
                user_id=user_b,
                business_id_str=business_id,
                order_number=1,
            )

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_order_creation_yields_unique_sequential_numbers() -> None:
    """Done when: concurrent order creation yields unique sequential numbers without gaps."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    service = OrderService(session_factory=session_factory)
    user_id = uuid.uuid4()

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            from sahayak.modules.business.adapters.orders import SQLAlchemyBusinessRepository

            b_repo = SQLAlchemyBusinessRepository(uow.session)
            biz, _ = await b_repo.get_or_create_default_business(
                user_id=user_id, name="Concurrency Store"
            )
            biz_id_str = str(biz.id)
            await uow.session.commit()

        # Create 20 orders concurrently on this business
        async def create_one(idx: int) -> int:
            data, _, _ = await service.create_order(
                user_id=user_id,
                business_id_str=biz_id_str,
                customer_name=f"Customer {idx}",
                items=[{"item_name": f"Item {idx}", "quantity": 1, "unit_price_minor": 100}],
            )
            return int(data["order"]["order_number"])

        tasks = [create_one(i) for i in range(20)]
        results = await asyncio.gather(*tasks)

        # Assert all 20 order numbers are strictly unique and contiguous: 1 through 20
        assert len(results) == 20
        assert set(results) == set(range(1, 21)), f"Order numbers not sequential: {sorted(results)}"

    finally:
        await engine.dispose()
