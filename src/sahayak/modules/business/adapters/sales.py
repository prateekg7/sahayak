"""SQLAlchemy repository for product inventory and sales summaries (T10.3)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from sahayak.modules.business.models import Order, OrderItem, Product
from sahayak.modules.business.ports import ProductRepositoryPort


class SQLAlchemyProductRepository(ProductRepositoryPort):
    """Repository managing products, atomic stock decrements, and sales summaries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_or_update_product(
        self,
        *,
        business_id: uuid.UUID,
        name: str,
        stock_level: int,
        low_stock_threshold: int = 5,
        unit_price_minor: int = 0,
        sku: str | None = None,
    ) -> Product:
        """Create or update a product and its stock level."""
        clean_name = name.strip()
        now = datetime.now(UTC)

        stmt = select(Product).where(
            Product.business_id == business_id,
            func.lower(Product.name) == clean_name.lower(),
        )
        res = await self.session.execute(stmt)
        prod = res.scalar_one_or_none()

        if prod:
            prod.stock_level = stock_level
            prod.low_stock_threshold = low_stock_threshold
            prod.unit_price_minor = unit_price_minor
            if sku is not None:
                prod.sku = sku.strip()
            prod.updated_at = now
            await self.session.flush()
            return prod

        prod = Product(
            id=uuid.uuid4(),
            business_id=business_id,
            name=clean_name,
            sku=sku.strip() if sku else None,
            stock_level=stock_level,
            low_stock_threshold=low_stock_threshold,
            unit_price_minor=unit_price_minor,
            created_at=now,
            updated_at=now,
        )
        self.session.add(prod)
        await self.session.flush()
        return prod

    async def get_product(
        self,
        *,
        business_id: uuid.UUID,
        product_id: uuid.UUID,
    ) -> Product | None:
        """Find product by ID."""
        stmt = select(Product).where(
            Product.business_id == business_id,
            Product.id == product_id,
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def find_product_by_name(
        self,
        *,
        business_id: uuid.UUID,
        name: str,
    ) -> Product | None:
        """Find product by exact or case-insensitive name."""
        stmt = select(Product).where(
            Product.business_id == business_id,
            func.lower(Product.name) == name.strip().lower(),
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_products(
        self,
        *,
        business_id: uuid.UUID,
    ) -> list[Product]:
        """List all inventory products for a business."""
        stmt = (
            select(Product).where(Product.business_id == business_id).order_by(Product.name.asc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_low_stock_products(
        self,
        *,
        business_id: uuid.UUID,
    ) -> list[Product]:
        """List products whose stock_level is <= low_stock_threshold."""
        stmt = (
            select(Product)
            .where(
                Product.business_id == business_id,
                Product.stock_level <= Product.low_stock_threshold,
            )
            .order_by(Product.stock_level.asc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def decrement_stock_atomic(
        self,
        *,
        product_id: uuid.UUID,
        quantity: int,
    ) -> bool:
        """Atomically decrement stock if stock_level >= quantity. Return True if success."""
        stmt = (
            update(Product)
            .where(
                Product.id == product_id,
                Product.stock_level >= quantity,
            )
            .values(
                stock_level=Product.stock_level - quantity,
                updated_at=datetime.now(UTC),
            )
            .returning(Product.stock_level)
        )
        res = await self.session.execute(stmt)
        val = res.scalar_one_or_none()
        return val is not None

    async def get_sales_summary(
        self,
        *,
        business_id: uuid.UUID,
        start_time: datetime,
        end_time: datetime,
    ) -> dict[str, Any]:
        """Aggregate total revenue and order counts in time window."""
        stmt = select(Order).where(
            Order.business_id == business_id,
            Order.created_at >= start_time,
            Order.created_at <= end_time,
        )
        res = await self.session.execute(stmt)
        orders = list(res.scalars().all())

        total_orders = len(orders)
        active_orders = [o for o in orders if o.status != "cancelled"]
        revenue_minor = sum(o.total_amount_minor for o in active_orders)
        statuses: dict[str, int] = {}
        for o in orders:
            statuses[o.status] = statuses.get(o.status, 0) + 1

        return {
            "total_orders": total_orders,
            "active_orders": len(active_orders),
            "revenue_minor": revenue_minor,
            "status_breakdown": statuses,
        }

    async def get_top_selling_products(
        self,
        *,
        business_id: uuid.UUID,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Compute top products by units sold across orders."""
        stmt = (
            select(
                OrderItem.item_name,
                func.sum(OrderItem.quantity).label("units_sold"),
                func.sum(OrderItem.total_price_minor).label("revenue_minor"),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                Order.business_id == business_id,
                Order.status.in_(["packed", "shipped", "delivered"]),
            )
            .group_by(OrderItem.item_name)
            .order_by(desc("units_sold"))
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return [
            {
                "name": row[0],
                "units_sold": int(row[1]),
                "revenue_minor": int(row[2]),
            }
            for row in res.all()
        ]
