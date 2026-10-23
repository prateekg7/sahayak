"""Service and concurrency tests for sales summaries and stock decrement (T10.3)."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError
from sahayak.modules.business.adapters.orders import SQLAlchemyBusinessRepository
from sahayak.modules.business.adapters.sales import SQLAlchemyProductRepository
from sahayak.modules.business.service.orders import OrderService
from sahayak.modules.business.service.sales import SalesService
from sahayak.shared.users.models import User


@pytest.mark.asyncio
async def test_sales_summary_service_lifecycle_and_reporting() -> None:
    """Test product management, order placement, sales summary, and low stock detection."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    order_svc = OrderService(session_factory=session_factory)
    sales_svc = SalesService(session_factory=session_factory)
    user_id = uuid.uuid4()

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.commit()

        # 1. Register products
        _, data_p1 = await sales_svc.add_or_update_product(
            user_id=user_id,
            name="A4 Notebook",
            stock_level=50,
            low_stock_threshold=10,
            unit_price_minor=7500,
        )
        biz_id = data_p1["business_id"]

        await sales_svc.add_or_update_product(
            user_id=user_id,
            business_id=biz_id,
            name="Blue Gel Pen",
            stock_level=100,
            low_stock_threshold=20,
            unit_price_minor=1000,
        )

        await sales_svc.add_or_update_product(
            user_id=user_id,
            business_id=biz_id,
            name="Organic Milk",
            stock_level=3,  # Below threshold 5 -> low stock!
            low_stock_threshold=5,
            unit_price_minor=4500,
        )

        # 2. Check low stock products
        spoken_low, data_low = await sales_svc.get_low_stock(user_id=user_id, business_id=biz_id)
        assert data_low["count"] == 1
        assert data_low["low_stock_products"][0]["name"] == "Organic Milk"
        assert "Organic Milk has 3 units left" in spoken_low

        # 3. Create and ship an order
        data_order, _, _ = await order_svc.create_order(
            user_id=user_id,
            business_id_str=biz_id,
            customer_name="Sunita",
            items=[
                {"item_name": "A4 Notebook", "quantity": 4, "unit_price_minor": 7500},
                {"item_name": "Blue Gel Pen", "quantity": 10, "unit_price_minor": 1000},
            ],
        )
        order_num = data_order["order"]["order_number"]

        # Advance order to shipped (decrements stock)
        await order_svc.update_status(
            user_id=user_id,
            business_id_str=biz_id,
            order_number=order_num,
            new_status="packed",
        )
        await order_svc.update_status(
            user_id=user_id,
            business_id_str=biz_id,
            order_number=order_num,
            new_status="shipped",
        )

        # Verify stock decremented
        async with session_factory() as session:
            p_repo = SQLAlchemyProductRepository(session)
            prod_book = await p_repo.find_product_by_name(
                business_id=uuid.UUID(biz_id), name="A4 Notebook"
            )
            assert prod_book is not None
            assert prod_book.stock_level == 46  # 50 - 4

        # 4. Check today sales summary
        spoken_today, data_today = await sales_svc.get_today_summary(
            user_id=user_id, business_id=biz_id
        )
        assert data_today["summary"]["total_orders"] == 1
        assert data_today["summary"]["revenue_minor"] == 40000  # (4*7500) + (10*1000)
        assert "Today you had 1 order totaling 400 rupees." in spoken_today

        # 5. Check week sales summary
        _, data_week = await sales_svc.get_week_summary(user_id=user_id, business_id=biz_id)
        assert data_week["summary"]["total_orders"] == 1
        assert data_week["summary"]["revenue_minor"] == 40000

        # 6. Check top selling products
        spoken_top, data_top = await sales_svc.get_top_products(user_id=user_id, business_id=biz_id)
        top_names = [p["name"] for p in data_top["top_products"]]
        assert "Blue Gel Pen" in top_names  # 10 units
        assert "A4 Notebook" in top_names  # 4 units
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_order_shipping_never_allows_negative_stock() -> None:
    """Concurrency gate: stock never drops below zero when multiple orders race to ship."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    order_svc = OrderService(session_factory=session_factory)
    sales_svc = SalesService(session_factory=session_factory)
    user_id = uuid.uuid4()

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.commit()

        # Pre-create business
        async with session_factory() as session:
            b_repo = SQLAlchemyBusinessRepository(session)
            biz, _ = await b_repo.get_or_create_default_business(
                user_id=user_id, name="Stationery Store"
            )
            await session.commit()
            biz_id = str(biz.id)

        # Register product with exactly 10 units in stock
        await sales_svc.add_or_update_product(
            user_id=user_id,
            business_id=biz_id,
            name="Limited Edition Pen",
            stock_level=10,
            low_stock_threshold=2,
            unit_price_minor=5000,
        )

        # Create 10 separate orders, each wanting 2 units (Total demand = 20 units > 10 in stock)
        order_numbers: list[int] = []
        for i in range(10):
            data_o, _, _ = await order_svc.create_order(
                user_id=user_id,
                business_id_str=biz_id,
                customer_name=f"Customer {i}",
                items=[
                    {"item_name": "Limited Edition Pen", "quantity": 2, "unit_price_minor": 5000}
                ],
            )
            num = data_o["order"]["order_number"]
            # advance to packed first
            await order_svc.update_status(
                user_id=user_id,
                business_id_str=biz_id,
                order_number=num,
                new_status="packed",
            )
            order_numbers.append(num)

        # Concurrently attempt to ship all 10 orders
        async def try_ship_order(ord_num: int) -> bool:
            try:
                await order_svc.update_status(
                    user_id=user_id,
                    business_id_str=biz_id,
                    order_number=ord_num,
                    new_status="shipped",
                )
                return True
            except InvalidInputError as exc:
                assert "not enough stock" in str(exc.spoken)
                return False

        results = await asyncio.gather(*(try_ship_order(num) for num in order_numbers))

        succeeded_count = sum(1 for r in results if r is True)
        failed_count = sum(1 for r in results if r is False)

        # Exactly 5 orders (5 * 2 = 10 units) should have succeeded, and 5 must have failed!
        assert succeeded_count == 5
        assert failed_count == 5

        # Verify final stock is exactly zero and never negative
        async with session_factory() as session:
            p_repo = SQLAlchemyProductRepository(session)
            prod = await p_repo.find_product_by_name(
                business_id=uuid.UUID(biz_id), name="Limited Edition Pen"
            )
            assert prod is not None
            assert prod.stock_level == 0
    finally:
        await engine.dispose()
