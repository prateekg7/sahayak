"""The 'budget' MCP tool for monthly category budgets and run-rate tracking (T6.2)."""

from __future__ import annotations

import logging
from typing import Any

from sahayak.core.auth.principal import get_current_principal, requires
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import AuthRequiredError, SahayakError
from sahayak.core.idempotency import idempotent
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.finance.schemas import BudgetAction, BudgetRequest
from sahayak.modules.finance.service.budgets import BudgetService

logger = logging.getLogger(__name__)

_budget_service: BudgetService | None = None


def set_budget_service(service: BudgetService) -> None:
    """Inject the active BudgetService instance."""
    global _budget_service
    _budget_service = service


def get_budget_service() -> BudgetService:
    """Retrieve the injected BudgetService instance."""
    if _budget_service is None:
        raise RuntimeError("BudgetService has not been initialized.")
    return _budget_service


BUDGET_DESCRIPTION = (
    "Manage monthly category budgets and track spending against targets. "
    "Use when the user says 'Set groceries budget to 5000 rupees', "
    "'How much grocery budget do I have left?', 'List my budgets', or 'Remove my dining budget'. "
    "Do not use for logging individual transactions; use expense_log instead."
)


@requires()
@idempotent(tool_name="budget")
@instrument_tool("budget", "finance")
async def budget(
    action: str,
    category: str | None = None,
    amount: str | int | None = None,
    currency: str = "INR",
    timezone: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Execute category budget operations (set, status, list, remove)."""
    principal = get_current_principal()
    if principal is None or principal.anonymous or principal.user_id is None:
        raise AuthRequiredError(
            spoken="Please link your account in the Alexa app to manage your budgets.",
            detail="Account linking required for budget tool",
        )

    try:
        req = BudgetRequest(
            action=BudgetAction(action.strip().lower()),
            category=category,
            amount=amount,
            currency=currency,
            timezone=timezone,
            request_id=request_id,
        )

        service = get_budget_service()
        data, spoken = await service.execute(user_id=principal.user_id, request=req)

        next_actions = ["budget(action='status')", "budget(action='list')"]
        if req.action == BudgetAction.SET:
            next_actions = [f"budget(action='status', category='{req.category}')"]
        elif req.action == BudgetAction.REMOVE:
            next_actions = ["budget(action='list')"]

        return ok(
            spoken_summary=spoken,
            data=data.model_dump(),
            next_actions=next_actions,
            module="finance",
            version="0.1.0",
        )
    except SahayakError as err:
        return fail(err, module="finance", version="0.1.0")
    except Exception as exc:
        logger.exception("Unexpected error in budget tool: %s", exc)
        return fail(SahayakError(), module="finance", version="0.1.0")
