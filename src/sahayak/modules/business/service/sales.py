"""Service orchestrating business sales summaries, top products, and inventory (T10.3)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.business.adapters.orders import SQLAlchemyBusinessRepository
from sahayak.modules.business.adapters.sales import SQLAlchemyProductRepository
from sahayak.modules.business.domain.sales import (
    format_low_stock_spoken,
    format_product_added_spoken,
    format_sales_today_spoken,
    format_sales_week_spoken,
    format_top_products_spoken,
)


class SalesService:
    """Service providing sales reporting, top selling analytics, and low stock monitoring."""

    def __init__(self, session_factory: Any) -> None:
        self.session_factory = session_factory

    async def _resolve_business_id(
        self,
        *,
        user_id: uuid.UUID,
        business_id_str: str | None,
        uow: UnitOfWork,
    ) -> tuple[uuid.UUID, str]:
        """Resolve business ID and currency, auto-creating default store if needed."""
        b_repo = SQLAlchemyBusinessRepository(uow.session)

        if business_id_str and business_id_str.strip():
            try:
                b_id = uuid.UUID(business_id_str.strip())
            except ValueError as err:
                raise InvalidInputError("Invalid business ID format.") from err

            membership = await b_repo.get_membership(business_id=b_id, user_id=user_id)
            if not membership:
                raise NotFoundError(
                    spoken="You do not have access to that business.",
                    detail=f"User {user_id} is not a member of business {b_id}",
                )
            business = await b_repo.get_business(business_id=b_id)
            currency = business.currency if business else "INR"
            return b_id, currency

        business, _ = await b_repo.get_or_create_default_business(
            user_id=user_id,
            name="My Store",
        )
        return business.id, business.currency

    async def get_today_summary(
        self,
        *,
        user_id: uuid.UUID,
        business_id: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Compute sales summary for today."""
        now = datetime.now(UTC)
        start_of_today = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=UTC)

        async with UnitOfWork(self.session_factory) as uow:
            b_id, currency = await self._resolve_business_id(
                user_id=user_id,
                business_id_str=business_id,
                uow=uow,
            )
            p_repo = SQLAlchemyProductRepository(uow.session)
            summary = await p_repo.get_sales_summary(
                business_id=b_id,
                start_time=start_of_today,
                end_time=now,
            )

            spoken = format_sales_today_spoken(
                revenue_minor=summary["revenue_minor"],
                order_count=summary["total_orders"],
                currency=currency,
            )
            data = {
                "business_id": str(b_id),
                "period": "today",
                "summary": summary,
                "currency": currency,
            }
            return spoken, data

    async def get_week_summary(
        self,
        *,
        user_id: uuid.UUID,
        business_id: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Compute sales summary for past 7 days."""
        now = datetime.now(UTC)
        start_of_week = now - timedelta(days=7)

        async with UnitOfWork(self.session_factory) as uow:
            b_id, currency = await self._resolve_business_id(
                user_id=user_id,
                business_id_str=business_id,
                uow=uow,
            )
            p_repo = SQLAlchemyProductRepository(uow.session)
            summary = await p_repo.get_sales_summary(
                business_id=b_id,
                start_time=start_of_week,
                end_time=now,
            )

            spoken = format_sales_week_spoken(
                revenue_minor=summary["revenue_minor"],
                order_count=summary["total_orders"],
                currency=currency,
            )
            data = {
                "business_id": str(b_id),
                "period": "week",
                "summary": summary,
                "currency": currency,
            }
            return spoken, data

    async def get_top_products(
        self,
        *,
        user_id: uuid.UUID,
        business_id: str | None = None,
        limit: int = 5,
    ) -> tuple[str, dict[str, Any]]:
        """Compute top selling products by units sold."""
        async with UnitOfWork(self.session_factory) as uow:
            b_id, currency = await self._resolve_business_id(
                user_id=user_id,
                business_id_str=business_id,
                uow=uow,
            )
            p_repo = SQLAlchemyProductRepository(uow.session)
            top_products = await p_repo.get_top_selling_products(
                business_id=b_id,
                limit=limit,
            )

            spoken = format_top_products_spoken(top_products, currency)
            data = {
                "business_id": str(b_id),
                "top_products": top_products,
                "currency": currency,
            }
            return spoken, data

    async def get_low_stock(
        self,
        *,
        user_id: uuid.UUID,
        business_id: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Fetch items at or below low stock threshold."""
        async with UnitOfWork(self.session_factory) as uow:
            b_id, currency = await self._resolve_business_id(
                user_id=user_id,
                business_id_str=business_id,
                uow=uow,
            )
            p_repo = SQLAlchemyProductRepository(uow.session)
            low_stock_prods = await p_repo.get_low_stock_products(business_id=b_id)
            prods_dict = [p.to_dict() for p in low_stock_prods]

            spoken = format_low_stock_spoken(prods_dict)
            data = {
                "business_id": str(b_id),
                "low_stock_products": prods_dict,
                "count": len(prods_dict),
                "currency": currency,
            }
            return spoken, data

    async def add_or_update_product(
        self,
        *,
        user_id: uuid.UUID,
        business_id: str | None = None,
        name: str | None = None,
        stock_level: int | None = None,
        low_stock_threshold: int | None = 5,
        unit_price_minor: int | None = 0,
        sku: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Add or update an inventory product."""
        if not name or not name.strip():
            raise InvalidInputError(
                spoken="Please specify the product name.",
                detail="Product name is required",
            )
        if stock_level is None or stock_level < 0:
            raise InvalidInputError(
                spoken="Stock level must be zero or a positive number.",
                detail="stock_level must be >= 0",
            )
        thresh = (
            low_stock_threshold
            if low_stock_threshold is not None and low_stock_threshold >= 0
            else 5
        )
        price_minor = (
            unit_price_minor if unit_price_minor is not None and unit_price_minor >= 0 else 0
        )

        async with UnitOfWork(self.session_factory) as uow:
            b_id, currency = await self._resolve_business_id(
                user_id=user_id,
                business_id_str=business_id,
                uow=uow,
            )
            p_repo = SQLAlchemyProductRepository(uow.session)
            prod = await p_repo.create_or_update_product(
                business_id=b_id,
                name=name.strip(),
                stock_level=stock_level,
                low_stock_threshold=thresh,
                unit_price_minor=price_minor,
                sku=sku,
            )

            spoken = format_product_added_spoken(
                name=prod.name,
                stock_level=prod.stock_level,
                threshold=prod.low_stock_threshold,
            )
            data = {
                "business_id": str(b_id),
                "product": prod.to_dict(),
                "currency": currency,
            }
            return spoken, data

    async def list_products(
        self,
        *,
        user_id: uuid.UUID,
        business_id: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """List all inventory products for a business."""
        async with UnitOfWork(self.session_factory) as uow:
            b_id, currency = await self._resolve_business_id(
                user_id=user_id,
                business_id_str=business_id,
                uow=uow,
            )
            p_repo = SQLAlchemyProductRepository(uow.session)
            prods = await p_repo.list_products(business_id=b_id)
            prods_dict = [p.to_dict() for p in prods]

            if not prods_dict:
                spoken = "You have no products registered in your inventory."
            else:
                names = [f"{p['name']} ({p['stock_level']} units)" for p in prods_dict[:5]]
                spoken = f"You have {len(prods_dict)} products: " + ", ".join(names) + "."
                if len(prods_dict) > 5:
                    spoken += f" Plus {len(prods_dict) - 5} more products."
            spoken = spoken[:300]

            data = {
                "business_id": str(b_id),
                "products": prods_dict,
                "count": len(prods_dict),
                "currency": currency,
            }
            return spoken, data
