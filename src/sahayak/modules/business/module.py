"""Business module conforming to the Module protocol (T10.1)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select

from sahayak.core.db.session import UnitOfWork
from sahayak.core.module import Deps, HealthStatus
from sahayak.modules.business.models import (
    Business,
    BusinessMember,
    Customer,
    Order,
    OrderItem,
)


class BusinessModule:
    """Small business module providing business tenancy, customer orders, and tracking."""

    def __init__(self) -> None:
        self._deps: Deps | None = None
        self._api: Any = None

    @property
    def name(self) -> str:
        return "business"

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def api(self) -> Any:
        if self._api is None:
            if self._deps is None or self._deps.session_factory is None:
                return None
            from sahayak.modules.business.api import BusinessAPI

            self._api = BusinessAPI(session_factory=self._deps.session_factory)
        return self._api

    def register_tools(self, mcp: Any, deps: Deps) -> None:
        """Register MCP tools for business module."""
        self._deps = deps
        if deps.session_factory is not None:
            from sahayak.modules.business.service.orders import OrderService
            from sahayak.modules.business.tools.orders import set_order_service

            order_service = OrderService(session_factory=deps.session_factory)
            set_order_service(order_service)

        from sahayak.modules.business.tools.orders import (
            ORDERS_DESCRIPTION,
            orders,
        )

        tool_decorator = getattr(mcp, "tool", None)
        if callable(tool_decorator):
            tool_decorator(name="orders", description=ORDERS_DESCRIPTION)(orders)
        elif hasattr(mcp, "add_tool"):
            mcp.add_tool(orders, name="orders", description=ORDERS_DESCRIPTION)

    def register_jobs(self, worker: Any) -> None:
        """Register background worker jobs for business module."""
        pass

    def migrations_path(self) -> str | None:
        return str(Path(__file__).parent / "migrations")

    def health(self) -> HealthStatus:
        if self._deps is not None and self._deps.session_factory is None:
            return HealthStatus(healthy=False, detail="PostgreSQL session factory missing")
        return HealthStatus(healthy=True, detail="Business module is operational")

    def on_event(self, event: Any) -> None:
        """Dispatched domain events hook."""
        pass

    async def export_user_data(self, user_id: str) -> dict[str, Any]:
        """GDPR Right to Access: export businesses, memberships, orders, customers."""
        if self._deps is None or self._deps.session_factory is None:
            return {}

        uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        async with UnitOfWork(self._deps.session_factory) as uow:
            res_m = await uow.session.execute(
                select(BusinessMember).where(BusinessMember.user_id == uid)
            )
            memberships = res_m.scalars().all()
            b_ids = [m.business_id for m in memberships]

            exported_businesses = []
            exported_orders = []
            exported_items = []
            exported_customers = []

            if b_ids:
                res_b = await uow.session.execute(select(Business).where(Business.id.in_(b_ids)))
                exported_businesses = [b.to_dict() for b in res_b.scalars().all()]

                res_o = await uow.session.execute(select(Order).where(Order.business_id.in_(b_ids)))
                orders_list = res_o.scalars().all()
                exported_orders = [o.to_dict() for o in orders_list]

                order_ids = [o.id for o in orders_list]
                if order_ids:
                    res_i = await uow.session.execute(
                        select(OrderItem).where(OrderItem.order_id.in_(order_ids))
                    )
                    exported_items = [it.to_dict() for it in res_i.scalars().all()]

                res_c = await uow.session.execute(
                    select(Customer).where(Customer.business_id.in_(b_ids))
                )
                exported_customers = [c.to_dict() for c in res_c.scalars().all()]

            return {
                "businesses": exported_businesses,
                "memberships": [m.to_dict() for m in memberships],
                "orders": exported_orders,
                "order_items": exported_items,
                "customers": exported_customers,
            }

    async def delete_user_data(self, user_id: str) -> None:
        """GDPR Right to Erasure: scrub user membership records and handle tenancy ownership."""
        if self._deps is None or self._deps.session_factory is None:
            return

        uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        async with UnitOfWork(self._deps.session_factory) as uow:
            res_m = await uow.session.execute(
                select(BusinessMember).where(BusinessMember.user_id == uid)
            )
            user_memberships = list(res_m.scalars().all())

            for m in user_memberships:
                all_members_res = await uow.session.execute(
                    select(BusinessMember).where(BusinessMember.business_id == m.business_id)
                )
                all_members = list(all_members_res.scalars().all())
                other_members = [om for om in all_members if om.user_id != uid]

                if not other_members:
                    # Sole member: delete entire business (cascades orders, items, customers)
                    await uow.session.execute(delete(Business).where(Business.id == m.business_id))
                else:
                    if m.role == "owner":
                        # Transfer ownership to earliest joined member
                        earliest = sorted(other_members, key=lambda x: x.joined_at)[0]
                        earliest.role = "owner"
                    await uow.session.execute(
                        delete(BusinessMember).where(
                            BusinessMember.business_id == m.business_id,
                            BusinessMember.user_id == uid,
                        )
                    )


module = BusinessModule()
