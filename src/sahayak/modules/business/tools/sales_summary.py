"""The 'sales_summary' MCP tool for sales reporting and inventory stock alerts (T10.3)."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from sahayak.core.auth.principal import get_current_principal, requires
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import AuthRequiredError, InvalidInputError, SahayakError
from sahayak.core.idempotency import idempotent
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.business.schemas import SalesSummaryAction, SalesSummaryRequest
from sahayak.modules.business.service.sales import SalesService

logger = logging.getLogger(__name__)

_sales_service: SalesService | None = None


def set_sales_service(service: SalesService) -> None:
    """Inject the active SalesService instance."""
    global _sales_service
    _sales_service = service


def get_sales_service() -> SalesService:
    """Retrieve the injected SalesService instance."""
    if _sales_service is None:
        raise RuntimeError("SalesService has not been initialized.")
    return _sales_service


SALES_SUMMARY_DESCRIPTION = (
    "Inspect business sales summaries and low stock alerts. "
    "Use when the user says 'How were sales today?', 'What were this week's sales?', "
    "'What are my top products?', 'Any items low in stock?', or 'Add product Milk with 50 units'. "
    "Do not use for individual order details; use orders instead."
)


@requires()
@idempotent(tool_name="sales_summary")
@instrument_tool("sales_summary", "business")
async def sales_summary(
    action: str = "today",
    business_id: str | None = None,
    name: str | None = None,
    stock_level: int | None = None,
    low_stock_threshold: int | None = 5,
    unit_price: float | None = None,
    unit_price_minor: int | None = None,
    sku: str | None = None,
    limit: int = 5,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Execute sales summary operations: today, week, top_products, low_stock, add_product."""
    principal = get_current_principal()
    if principal is None or principal.anonymous or principal.user_id is None:
        raise AuthRequiredError(
            spoken="Please link your account in the Alexa app to view sales summaries.",
            detail="User principal is anonymous or unauthenticated",
        )

    try:
        req = SalesSummaryRequest(
            action=action,  # type: ignore[arg-type]
            business_id=business_id,
            name=name,
            stock_level=stock_level,
            low_stock_threshold=low_stock_threshold,
            unit_price=unit_price,
            unit_price_minor=unit_price_minor,
            sku=sku,
            limit=limit,
            request_id=request_id,
        )
    except ValidationError as exc:
        msg = exc.errors()[0]["msg"] if exc.errors() else "Invalid input"
        raise InvalidInputError(
            spoken="The sales summary parameters were invalid. Please try again.",
            detail=f"Validation failed: {msg}",
        ) from exc

    service = get_sales_service()
    user_id = principal.user_id

    try:
        next_actions: list[str] = []
        if req.action == SalesSummaryAction.TODAY:
            spoken, data = await service.get_today_summary(
                user_id=user_id,
                business_id=req.business_id,
            )
            next_actions = [
                "sales_summary(action='week')",
                "sales_summary(action='top_products')",
                "sales_summary(action='low_stock')",
            ]
        elif req.action == SalesSummaryAction.WEEK:
            spoken, data = await service.get_week_summary(
                user_id=user_id,
                business_id=req.business_id,
            )
            next_actions = [
                "sales_summary(action='today')",
                "sales_summary(action='top_products')",
            ]
        elif req.action == SalesSummaryAction.TOP_PRODUCTS:
            spoken, data = await service.get_top_products(
                user_id=user_id,
                business_id=req.business_id,
                limit=req.limit,
            )
            next_actions = [
                "sales_summary(action='today')",
                "sales_summary(action='low_stock')",
            ]
        elif req.action == SalesSummaryAction.LOW_STOCK:
            spoken, data = await service.get_low_stock(
                user_id=user_id,
                business_id=req.business_id,
            )
            next_actions = [
                "sales_summary(action='add_product', name='Item', stock_level=50)",
                "sales_summary(action='today')",
            ]
        elif req.action == SalesSummaryAction.ADD_PRODUCT:
            spoken, data = await service.add_or_update_product(
                user_id=user_id,
                business_id=req.business_id,
                name=req.name,
                stock_level=req.stock_level,
                low_stock_threshold=req.low_stock_threshold,
                unit_price_minor=req.unit_price_minor,
                sku=req.sku,
            )
            next_actions = [
                "sales_summary(action='low_stock')",
                "sales_summary(action='list_products')",
            ]
        elif req.action == SalesSummaryAction.LIST_PRODUCTS:
            spoken, data = await service.list_products(
                user_id=user_id,
                business_id=req.business_id,
            )
            next_actions = [
                "sales_summary(action='low_stock')",
                "sales_summary(action='today')",
            ]
        else:
            raise InvalidInputError(
                spoken="I could not recognize that sales summary action.",
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
        logger.exception("Unexpected error executing sales_summary tool: %s", exc)
        return fail(SahayakError(), module="business", version="0.1.0")
