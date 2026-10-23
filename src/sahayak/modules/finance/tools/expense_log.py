"""The 'expense_log' MCP tool for personal spending management (T6.1)."""

from __future__ import annotations

import logging
from typing import Any

from sahayak.core.auth.principal import get_current_principal, requires
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import AuthRequiredError, InvalidInputError, SahayakError
from sahayak.core.idempotency import idempotent
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.finance.schemas import ExpenseAction, ExpenseLogRequest
from sahayak.modules.finance.service.expenses import ExpenseService

logger = logging.getLogger(__name__)

_expense_service: ExpenseService | None = None


def set_expense_service(service: ExpenseService) -> None:
    """Inject the active ExpenseService instance."""
    global _expense_service
    _expense_service = service


def get_expense_service() -> ExpenseService:
    """Retrieve the injected ExpenseService instance."""
    if _expense_service is None:
        raise RuntimeError("ExpenseService has not been initialized.")
    return _expense_service


EXPENSE_LOG_DESCRIPTION = (
    "Track personal spending, log expenses by category, list recent purchases, and undo entries. "
    "Use when the user says 'Add 200 rupees for groceries', 'What did I spend this week?', "
    "'List my expenses', or 'Undo my last expense'. "
    "Do not use for monthly budget targets; use the budget tool instead."
)


@requires()
@idempotent(tool_name="expense_log")
@instrument_tool("expense_log", "finance")
async def expense_log(
    action: str,
    amount: str | int | None = None,
    currency: str = "INR",
    category: str | None = None,
    note: str | None = None,
    expense_id: str | None = None,
    limit: int = 5,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Execute personal expense operations (add, list, undo_last, delete)."""
    principal = get_current_principal()
    if principal is None or principal.anonymous or principal.user_id is None:
        raise AuthRequiredError(
            spoken="Please link your account in the Alexa app to log and view your expenses.",
            detail="Account linking required for expense_log tool",
        )

    try:
        req = ExpenseLogRequest(
            action=ExpenseAction(action.strip().lower()),
            amount=amount,
            currency=currency,
            category=category,
            note=note,
            expense_id=expense_id,
            limit=limit,
            request_id=request_id,
        )

        service = get_expense_service()

        if req.action == ExpenseAction.ADD:
            spoken, data, next_actions = await service.add_expense(
                user_id=principal.user_id,
                amount=req.amount,
                currency=req.currency,
                category=req.category,
                note=req.note,
            )
        elif req.action == ExpenseAction.LIST:
            spoken, data, next_actions = await service.list_expenses(
                user_id=principal.user_id,
                category=req.category,
                limit=req.limit,
                currency=req.currency,
            )
        elif req.action == ExpenseAction.UNDO_LAST:
            spoken, data, next_actions = await service.undo_last_expense(
                user_id=principal.user_id,
            )
        elif req.action == ExpenseAction.DELETE:
            spoken, data, next_actions = await service.delete_expense(
                user_id=principal.user_id,
                expense_id_str=req.expense_id,
            )
        else:
            raise InvalidInputError(
                spoken=f"Unsupported action {req.action}.",
                detail=f"Unsupported expense action '{req.action}'",
            )

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
        logger.exception("Unexpected error in expense_log tool: %s", exc)
        return fail(SahayakError(), module="finance", version="0.1.0")
