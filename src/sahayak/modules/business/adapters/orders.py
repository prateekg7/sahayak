"""SQLAlchemy repositories for business tenancy and orders (T10.1)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from sahayak.modules.business.models import Business, BusinessMember, Order, OrderItem
from sahayak.modules.business.ports import BusinessRepositoryPort, OrderRepositoryPort


class SQLAlchemyBusinessRepository(BusinessRepositoryPort):
    """Repository handling business tenancy and membership in PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create_default_business(
        self,
        *,
        user_id: uuid.UUID,
        name: str = "My Store",
        currency: str = "INR",
    ) -> tuple[Business, BusinessMember]:
        """Retrieve existing business or create default store for user."""
        stmt = (
            select(Business, BusinessMember)
            .join(BusinessMember, Business.id == BusinessMember.business_id)
            .where(BusinessMember.user_id == user_id)
            .order_by(BusinessMember.joined_at.asc())
        )
        res = await self.session.execute(stmt)
        row = res.first()
        if row:
            return row[0], row[1]

        now = datetime.now(UTC)
        business_id = uuid.uuid4()
        business = Business(
            id=business_id,
            name=name.strip() or "My Store",
            currency=currency.upper(),
            order_seq=0,
            created_at=now,
            updated_at=now,
        )
        self.session.add(business)

        member = BusinessMember(
            id=uuid.uuid4(),
            business_id=business_id,
            user_id=user_id,
            role="owner",
            joined_at=now,
        )
        self.session.add(member)
        await self.session.flush()
        return business, member

    async def get_business(self, *, business_id: uuid.UUID) -> Business | None:
        """Retrieve business by ID."""
        return await self.session.get(Business, business_id)

    async def get_membership(
        self,
        *,
        business_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> BusinessMember | None:
        """Check if user has access to the business."""
        stmt = select(BusinessMember).where(
            BusinessMember.business_id == business_id,
            BusinessMember.user_id == user_id,
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_user_businesses(
        self,
        *,
        user_id: uuid.UUID,
    ) -> list[tuple[Business, BusinessMember]]:
        """List all businesses user belongs to."""
        stmt = (
            select(Business, BusinessMember)
            .join(BusinessMember, Business.id == BusinessMember.business_id)
            .where(BusinessMember.user_id == user_id)
            .order_by(Business.name.asc())
        )
        res = await self.session.execute(stmt)
        return list(res.all())


class SQLAlchemyOrderRepository(OrderRepositoryPort):
    """Repository handling atomic sequential orders and line items."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_order(
        self,
        *,
        business_id: uuid.UUID,
        customer_name: str | None,
        items: list[dict[str, Any]],
        notes: str | None = None,
        currency: str = "INR",
    ) -> tuple[Order, list[OrderItem]]:
        """Atomically generate the next sequential order number and create the order."""
        # Row-lock business row to atomically advance sequential order counter
        seq_stmt = (
            update(Business)
            .where(Business.id == business_id)
            .values(order_seq=Business.order_seq + 1)
            .returning(Business.order_seq)
        )
        seq_res = await self.session.execute(seq_stmt)
        order_seq_val = seq_res.scalar_one()

        now = datetime.now(UTC)
        order_id = uuid.uuid4()

        # Build line items and calculate total amount in minor units
        total_minor = 0
        order_items: list[OrderItem] = []
        for it in items:
            name = str(it.get("item_name", "Item")).strip()
            qty = max(1, int(it.get("quantity", 1)))
            unit_price = max(0, int(it.get("unit_price_minor", 0)))
            total_item_price = unit_price * qty
            total_minor += total_item_price

            item_obj = OrderItem(
                id=uuid.uuid4(),
                order_id=order_id,
                item_name=name,
                quantity=qty,
                unit_price_minor=unit_price,
                total_price_minor=total_item_price,
            )
            order_items.append(item_obj)
            self.session.add(item_obj)

        order = Order(
            id=order_id,
            business_id=business_id,
            order_number=order_seq_val,
            customer_name=customer_name.strip() if customer_name else None,
            status="pending",
            total_amount_minor=total_minor,
            currency=currency.upper(),
            notes=notes.strip() if notes else None,
            created_at=now,
            updated_at=now,
        )
        self.session.add(order)
        await self.session.flush()
        return order, order_items

    async def find_order_by_number(
        self,
        *,
        business_id: uuid.UUID,
        order_number: int,
    ) -> tuple[Order, list[OrderItem]] | None:
        """Find order and items by business ID and sequential order number."""
        stmt = select(Order).where(
            Order.business_id == business_id,
            Order.order_number == order_number,
        )
        res = await self.session.execute(stmt)
        order = res.scalar_one_or_none()
        if not order:
            return None

        items_stmt = (
            select(OrderItem)
            .where(OrderItem.order_id == order.id)
            .order_by(OrderItem.item_name.asc())
        )
        items_res = await self.session.execute(items_stmt)
        items = list(items_res.scalars().all())
        return order, items

    async def list_orders(
        self,
        *,
        business_id: uuid.UUID,
        statuses: list[str] | None = None,
        limit: int = 20,
    ) -> list[Order]:
        """List orders by business and optional status filter."""
        stmt = select(Order).where(Order.business_id == business_id)
        if statuses:
            stmt = stmt.where(Order.status.in_(statuses))

        stmt = stmt.order_by(Order.order_number.desc()).limit(limit)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def update_order_status(
        self,
        *,
        order_id: uuid.UUID,
        new_status: str,
    ) -> Order | None:
        """Update order status."""
        order = await self.session.get(Order, order_id)
        if not order:
            return None
        order.status = new_status
        order.updated_at = datetime.now(UTC)
        await self.session.flush()
        return order
