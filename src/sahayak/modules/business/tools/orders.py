"""The 'orders' MCP tool for customer order management and status tracking (T10.1)."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from sahayak.core.auth.principal import get_current_principal, requires
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import AuthRequiredError, InvalidInputError, SahayakError
from sahayak.core.idempotency import idempotent
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.business.schemas import OrderRequest
from sahayak.modules.business.service.orders import OrderService

logger = logging.getLogger(__name__)

_order_service: OrderService | None = None


def set_order_service(service: OrderService) -> None:
    """Inject the active OrderService instance."""
    global _order_service
    _order_service = service


def get_order_service() -> OrderService:
    """Retrieve the injected OrderService instance."""
    if _order_service is None:
        raise RuntimeError("OrderService has not been initialized.")
    return _order_service


ORDERS_DESCRIPTION = (
    "Create, track status, update, and inspect customer orders with sequential numbering. "
    "Use when the user says 'What orders are pending?', 'Mark order 12 shipped', "
    "'Create an order for Ramesh for 2 notebooks', or 'Check status of order 5'. "
    "Do not use for customer dues or unpaid balances; use ledger instead."
)


@requires()
@idempotent(tool_name="orders")
@instrument_tool("orders", "business")
async def orders(
    action: str = "list_pending",
    business_id: str | None = None,
    order_number: int | None = None,
    customer_name: str | None = None,
    items: list[dict[str, Any]] | None = None,
    status: str | None = None,
    notes: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Execute order operations: create, list_pending, update_status, get."""
    principal = get_current_principal()
    if principal is None or principal.anonymous or principal.user_id is None:
        raise AuthRequiredError(
            spoken="Please link your account in the Alexa app to manage business orders.",
            detail="User principal is anonymous or unauthenticated",
        )

    try:
        req = OrderRequest(
            action=action,  # type: ignore[arg-type]
            business_id=business_id,
            order_number=order_number,
            customer_name=customer_name,
            items=items,  # type: ignore[arg-type]
            status=status,
            notes=notes,
            request_id=request_id,
        )
    except ValidationError as exc:
        msg = exc.errors()[0]["msg"] if exc.errors() else "Invalid input"
        raise InvalidInputError(
            spoken="The order details provided were invalid. Please try again.",
            detail=f"Validation failed: {msg}",
        ) from exc

    service = get_order_service()
    user_id = principal.user_id

    try:
        if req.action == "create":
            items_payload = [it.model_dump() for it in req.items] if req.items else []
            data, spoken, next_actions = await service.create_order(
                user_id=user_id,
                business_id_str=req.business_id,
                customer_name=req.customer_name,
                items=items_payload,
                notes=req.notes,
            )
        elif req.action == "list_pending":
            data, spoken, next_actions = await service.list_pending(
                user_id=user_id,
                business_id_str=req.business_id,
            )
        elif req.action == "update_status":
            data, spoken, next_actions = await service.update_status(
                user_id=user_id,
                business_id_str=req.business_id,
                order_number=req.order_number,
                new_status=req.status,
            )
        elif req.action == "get":
            data, spoken, next_actions = await service.get_order(
                user_id=user_id,
                business_id_str=req.business_id,
                order_number=req.order_number,
            )
        else:
            raise InvalidInputError(
                spoken="I could not recognize that order action.",
                detail=f"Unsupported action: {req.action}",
            )

        return ok(
            spoken_summary=spoken,
            data=data,
            next_actions=next_actions,
            module="business",
            version="0.1.0",
        )
    except SahayakError as err:
        return fail(err, module="business", version="0.1.0")
    except Exception as exc:
        logger.exception("Unexpected error executing orders tool: %s", exc)
        return fail(SahayakError(), module="business", version="0.1.0")
