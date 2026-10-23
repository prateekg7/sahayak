"""Service orchestrating business order lifecycle and status transitions (T10.1)."""

from __future__ import annotations

import uuid
from typing import Any

from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.business.adapters.orders import (
    SQLAlchemyBusinessRepository,
    SQLAlchemyOrderRepository,
)
from sahayak.modules.business.domain.orders import (
    format_order_created_spoken,
    format_order_details_spoken,
    format_order_status_updated_spoken,
    format_pending_orders_spoken,
    validate_status_transition,
)


class OrderService:
    """Service managing customer orders, sequential numbering, and state transitions."""

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

    async def create_order(
        self,
        *,
        user_id: uuid.UUID,
        business_id_str: str | None = None,
        customer_name: str | None = None,
        items: list[dict[str, Any]] | None = None,
        notes: str | None = None,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Create a new order with atomic sequential number."""
        clean_items = items or []
        if not clean_items:
            raise InvalidInputError("Please specify at least one item for the order.")

        async with UnitOfWork(self.session_factory) as uow:
            b_id, currency = await self._resolve_business_id(
                user_id=user_id,
                business_id_str=business_id_str,
                uow=uow,
            )
            order_repo = SQLAlchemyOrderRepository(uow.session)
            order, order_items = await order_repo.create_order(
                business_id=b_id,
                customer_name=customer_name,
                items=clean_items,
                notes=notes,
                currency=currency,
            )
            order_dict = order.to_dict()
            items_dicts = [it.to_dict() for it in order_items]
            await uow.session.commit()

        num = order_dict["order_number"]
        spoken = format_order_created_spoken(
            order_number=num,
            total_minor=order_dict["total_amount_minor"],
            currency=currency,
            customer_name=customer_name,
        )
        data = {
            "business_id": str(b_id),
            "order": order_dict,
            "items": items_dicts,
        }
        next_actions = [
            f"orders(action='update_status', order_number={num}, status='packed')",
            f"orders(action='get', order_number={num})",
            "orders(action='list_pending')",
        ]
        return data, spoken, next_actions

    async def list_pending(
        self,
        *,
        user_id: uuid.UUID,
        business_id_str: str | None = None,
        statuses: list[str] | None = None,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """List active pending and in-progress orders."""
        target_statuses = statuses or ["pending", "packed", "shipped"]
        async with UnitOfWork(self.session_factory) as uow:
            b_id, _ = await self._resolve_business_id(
                user_id=user_id,
                business_id_str=business_id_str,
                uow=uow,
            )
            order_repo = SQLAlchemyOrderRepository(uow.session)
            orders = await order_repo.list_orders(
                business_id=b_id,
                statuses=target_statuses,
            )
            orders_dicts = [o.to_dict() for o in orders]

        spoken = format_pending_orders_spoken(orders_dicts)
        data = {
            "business_id": str(b_id),
            "orders": orders_dicts,
            "total_count": len(orders_dicts),
        }
        next_actions = ["orders(action='create', customer_name='...', items=[...])"]
        if orders_dicts:
            first_num = orders_dicts[0]["order_number"]
            next_actions.insert(0, f"orders(action='get', order_number={first_num})")
        return data, spoken, next_actions

    async def update_status(
        self,
        *,
        user_id: uuid.UUID,
        business_id_str: str | None = None,
        order_number: int | None,
        new_status: str | None,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Advance or change order status according to the state machine."""
        if order_number is None:
            raise InvalidInputError("Please specify an order number.")
        if not new_status or not new_status.strip():
            raise InvalidInputError(
                "Please specify the new status (e.g. packed, shipped, delivered, cancelled)."
            )

        clean_new_status = new_status.strip().lower()

        async with UnitOfWork(self.session_factory) as uow:
            b_id, _ = await self._resolve_business_id(
                user_id=user_id,
                business_id_str=business_id_str,
                uow=uow,
            )
            order_repo = SQLAlchemyOrderRepository(uow.session)
            found = await order_repo.find_order_by_number(
                business_id=b_id,
                order_number=order_number,
            )
            if not found:
                raise NotFoundError(
                    spoken=f"Order {order_number} was not found.",
                    detail=f"Order {order_number} not found in business {b_id}",
                )

            order, _ = found
            # Enforce state machine transition
            validate_status_transition(
                current_status=order.status,
                new_status=clean_new_status,
                order_number=order_number,
            )

            updated = await order_repo.update_order_status(
                order_id=order.id,
                new_status=clean_new_status,
            )
            order_dict = updated.to_dict() if updated else order.to_dict()
            await uow.session.commit()

        spoken = format_order_status_updated_spoken(order_number, clean_new_status)
        data = {
            "business_id": str(b_id),
            "order": order_dict,
        }
        next_actions = [
            f"orders(action='get', order_number={order_number})",
            "orders(action='list_pending')",
        ]
        return data, spoken, next_actions

    async def get_order(
        self,
        *,
        user_id: uuid.UUID,
        business_id_str: str | None = None,
        order_number: int | None,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Retrieve order and line item details by order number."""
        if order_number is None:
            raise InvalidInputError("Please specify an order number.")

        async with UnitOfWork(self.session_factory) as uow:
            b_id, _ = await self._resolve_business_id(
                user_id=user_id,
                business_id_str=business_id_str,
                uow=uow,
            )
            order_repo = SQLAlchemyOrderRepository(uow.session)
            found = await order_repo.find_order_by_number(
                business_id=b_id,
                order_number=order_number,
            )
            if not found:
                raise NotFoundError(
                    spoken=f"Order {order_number} was not found.",
                    detail=f"Order {order_number} not found in business {b_id}",
                )

            order, items = found
            order_dict = order.to_dict()
            items_dicts = [it.to_dict() for it in items]

        spoken = format_order_details_spoken(order_dict, items_dicts)
        data = {
            "business_id": str(b_id),
            "order": order_dict,
            "items": items_dicts,
        }
        next_actions = [
            f"orders(action='update_status', order_number={order_number}, status='...')",
            "orders(action='list_pending')",
        ]
        return data, spoken, next_actions
