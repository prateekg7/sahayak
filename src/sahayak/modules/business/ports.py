"""Repository ports for the business module (T10.1)."""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from sahayak.modules.business.models import Business, BusinessMember, Order, OrderItem


class BusinessRepositoryPort(Protocol):
    """Port for business tenancy and membership management."""

    async def get_or_create_default_business(
        self,
        *,
        user_id: uuid.UUID,
        name: str = "My Store",
        currency: str = "INR",
    ) -> tuple[Business, BusinessMember]:
        """Retrieve existing business or create default store for user."""
        ...

    async def get_business(self, *, business_id: uuid.UUID) -> Business | None:
        """Retrieve business by ID."""
        ...

    async def get_membership(
        self,
        *,
        business_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> BusinessMember | None:
        """Check if user has access to the business."""
        ...

    async def list_user_businesses(
        self,
        *,
        user_id: uuid.UUID,
    ) -> list[tuple[Business, BusinessMember]]:
        """List all businesses user belongs to."""
        ...


class OrderRepositoryPort(Protocol):
    """Port for customer orders and line items."""

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
        ...

    async def find_order_by_number(
        self,
        *,
        business_id: uuid.UUID,
        order_number: int,
    ) -> tuple[Order, list[OrderItem]] | None:
        """Find order and items by business ID and sequential order number."""
        ...

    async def list_orders(
        self,
        *,
        business_id: uuid.UUID,
        statuses: list[str] | None = None,
        limit: int = 20,
    ) -> list[Order]:
        """List orders by business and optional status filter."""
        ...

    async def update_order_status(
        self,
        *,
        order_id: uuid.UUID,
        new_status: str,
    ) -> Order | None:
        """Update order status."""
        ...
