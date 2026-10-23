"""The 'ledger' MCP tool for customer dues, credit, and payments (T10.2)."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from sahayak.core.auth.principal import get_current_principal, requires
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import AuthRequiredError, InvalidInputError, SahayakError
from sahayak.core.idempotency import idempotent
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.business.schemas import LedgerAction, LedgerRequest
from sahayak.modules.business.service.ledger import LedgerService

logger = logging.getLogger(__name__)

_ledger_service: LedgerService | None = None


def set_ledger_service(service: LedgerService) -> None:
    """Inject the active LedgerService instance."""
    global _ledger_service
    _ledger_service = service


def get_ledger_service() -> LedgerService:
    """Retrieve the injected LedgerService instance."""
    if _ledger_service is None:
        raise RuntimeError("LedgerService has not been initialized.")
    return _ledger_service


LEDGER_DESCRIPTION = (
    "Manage customer credit, dues, and payments for a small business. "
    "Use when the user says 'Ramesh owes 200 rupees', 'Record 500 payment from Priya', "
    "'How much does Anita owe', or 'Who owes me money'. "
    "Do not use for product orders; use orders instead."
)


@requires()
@idempotent(tool_name="ledger")
@instrument_tool("ledger", "business")
async def ledger(
    action: str = "top_dues",
    business_id: str | None = None,
    customer_name: str | None = None,
    customer_phone: str | None = None,
    customer_id: str | None = None,
    amount: float | None = None,
    amount_minor: int | None = None,
    notes: str | None = None,
    reference_id: str | None = None,
    entry_id: str | None = None,
    limit: int = 5,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Execute customer ledger operations: dues, payments, balances, reversals."""
    principal = get_current_principal()
    if principal is None or principal.anonymous or principal.user_id is None:
        raise AuthRequiredError(
            spoken="Please link your account in the Alexa app to manage customer dues.",
            detail="User principal is anonymous or unauthenticated",
        )

    try:
        req = LedgerRequest(
            action=action,  # type: ignore[arg-type]
            business_id=business_id,
            customer_name=customer_name,
            customer_phone=customer_phone,
            customer_id=customer_id,
            amount=amount,
            amount_minor=amount_minor,
            notes=notes,
            reference_id=reference_id,
            entry_id=entry_id,
            limit=limit,
            request_id=request_id,
        )
    except ValidationError as exc:
        msg = exc.errors()[0]["msg"] if exc.errors() else "Invalid input"
        raise InvalidInputError(
            spoken="The ledger details provided were invalid. Please try again.",
            detail=f"Validation failed: {msg}",
        ) from exc

    service = get_ledger_service()
    user_id = principal.user_id

    try:
        next_actions: list[str] = []
        if req.action == LedgerAction.ADD_DUE:
            spoken, data = await service.add_due(
                user_id=user_id,
                business_id=req.business_id,
                customer_name=req.customer_name,
                customer_phone=req.customer_phone,
                amount_minor=req.amount_minor,
                notes=req.notes,
                reference_id=req.reference_id,
            )
            next_actions = [
                f"Check balance with ledger(action='balance', customer_name='{req.customer_name}')",
                "View all outstanding dues with ledger(action='top_dues')",
            ]
        elif req.action == LedgerAction.RECORD_PAYMENT:
            spoken, data = await service.record_payment(
                user_id=user_id,
                business_id=req.business_id,
                customer_name=req.customer_name,
                customer_phone=req.customer_phone,
                amount_minor=req.amount_minor,
                notes=req.notes,
                reference_id=req.reference_id,
            )
            next_actions = [
                f"Check balance with ledger(action='balance', customer_name='{req.customer_name}')",
                "View all outstanding dues with ledger(action='top_dues')",
            ]
        elif req.action == LedgerAction.BALANCE:
            spoken, data = await service.get_balance(
                user_id=user_id,
                business_id=req.business_id,
                customer_name=req.customer_name,
                customer_phone=req.customer_phone,
                customer_id=req.customer_id,
            )
            cust_name = req.customer_name or "customer"
            next_actions = [
                f"Record payment with ledger(action='record_payment', customer_name='{cust_name}')",
                f"Add new due with ledger(action='add_due', customer_name='{cust_name}')",
            ]
        elif req.action == LedgerAction.TOP_DUES:
            spoken, data = await service.get_top_dues(
                user_id=user_id,
                business_id=req.business_id,
                limit=req.limit,
            )
            next_actions = [
                "Check balance with ledger(action='balance', customer_name='Name')",
                "Record payment with ledger(action='record_payment', customer_name='Name')",
            ]
        elif req.action == LedgerAction.REVERSE:
            spoken, data = await service.reverse_entry(
                user_id=user_id,
                business_id=req.business_id,
                entry_id=req.entry_id,
                notes=req.notes,
            )
            next_actions = [
                "Check balance with ledger(action='balance')",
                "View top dues with ledger(action='top_dues')",
            ]
        elif req.action == LedgerAction.RECONCILE:
            spoken, data = await service.reconcile_balances(
                user_id=user_id,
                business_id=req.business_id,
            )
            next_actions = ["View top dues with ledger(action='top_dues')"]
        else:
            raise InvalidInputError(
                spoken="I could not recognize that ledger action.",
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
        logger.exception("Unexpected error executing ledger tool: %s", exc)
        return fail(SahayakError(), module="business", version="0.1.0")
