"""Repository ports for the business module (T10.1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Protocol

from sahayak.modules.business.models import (
    Business,
    BusinessMember,
    Customer,
    LedgerEntry,
    Order,
    OrderItem,
    Product,
)


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


class LedgerRepositoryPort(Protocol):
    """Port for customer credit and debit ledger."""

    async def get_or_create_customer(
        self,
        *,
        business_id: uuid.UUID,
        name: str,
        phone: str | None = None,
    ) -> Customer:
        """Find existing customer by name/phone or create new one."""
        ...

    async def find_customer(
        self,
        *,
        business_id: uuid.UUID,
        customer_id: uuid.UUID | None = None,
        name: str | None = None,
        phone: str | None = None,
    ) -> Customer | None:
        """Find a customer by ID, exact name, or phone."""
        ...

    async def append_entry(
        self,
        *,
        business_id: uuid.UUID,
        customer_id: uuid.UUID,
        entry_type: str,
        direction: str,
        amount_minor: int,
        notes: str | None = None,
        reference_id: str | None = None,
        reversed_entry_id: uuid.UUID | None = None,
        created_by: uuid.UUID | None = None,
    ) -> LedgerEntry:
        """Append an immutable ledger entry."""
        ...

    async def get_entries_for_customer(
        self,
        *,
        business_id: uuid.UUID,
        customer_id: uuid.UUID,
    ) -> list[LedgerEntry]:
        """Fetch all ledger entries for a customer in chronological order."""
        ...

    async def get_entry_by_id(
        self,
        *,
        business_id: uuid.UUID,
        entry_id: uuid.UUID,
    ) -> LedgerEntry | None:
        """Fetch a specific ledger entry by ID."""
        ...

    async def get_top_dues(
        self,
        *,
        business_id: uuid.UUID,
        limit: int = 5,
    ) -> list[tuple[Customer, int]]:
        """Fetch customers with highest outstanding dues (positive balance)."""
        ...

    async def reconcile_all_balances(
        self,
        *,
        business_id: uuid.UUID,
    ) -> dict[uuid.UUID, int]:
        """Reconcile and compute current balances for all customers from ledger entries."""
        ...


class ProductRepositoryPort(Protocol):
    """Port for product inventory and sales summaries."""

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
        ...

    async def get_product(
        self,
        *,
        business_id: uuid.UUID,
        product_id: uuid.UUID,
    ) -> Product | None:
        """Find product by ID."""
        ...

    async def find_product_by_name(
        self,
        *,
        business_id: uuid.UUID,
        name: str,
    ) -> Product | None:
        """Find product by exact or case-insensitive name."""
        ...

    async def list_products(
        self,
        *,
        business_id: uuid.UUID,
    ) -> list[Product]:
        """List all inventory products for a business."""
        ...

    async def get_low_stock_products(
        self,
        *,
        business_id: uuid.UUID,
    ) -> list[Product]:
        """List products whose stock_level is <= low_stock_threshold."""
        ...

    async def decrement_stock_atomic(
        self,
        *,
        product_id: uuid.UUID,
        quantity: int,
    ) -> bool:
        """Atomically decrement stock if stock_level >= quantity. Return True if success."""
        ...

    async def get_sales_summary(
        self,
        *,
        business_id: uuid.UUID,
        start_time: datetime,
        end_time: datetime,
    ) -> dict[str, Any]:
        """Aggregate total revenue and order counts in time window."""
        ...

    async def get_top_selling_products(
        self,
        *,
        business_id: uuid.UUID,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Compute top products by units sold across orders."""
        ...
