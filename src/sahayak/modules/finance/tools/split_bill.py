"""The 'split_bill' MCP tool for shared expenses, balances, and settlements (T6.3)."""

from __future__ import annotations

import logging
from typing import Any

from sahayak.core.auth.principal import get_current_principal, requires
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import AuthRequiredError, SahayakError
from sahayak.core.idempotency import idempotent
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.finance.schemas import SplitBillAction, SplitBillRequest
from sahayak.modules.finance.service.split_bill import SplitBillService

logger = logging.getLogger(__name__)

_split_bill_service: SplitBillService | None = None


def set_split_bill_service(service: SplitBillService) -> None:
    """Inject the active SplitBillService instance."""
    global _split_bill_service
    _split_bill_service = service


def get_split_bill_service() -> SplitBillService:
    """Retrieve the injected SplitBillService instance."""
    if _split_bill_service is None:
        raise RuntimeError("SplitBillService has not been initialized.")
    return _split_bill_service


SPLIT_BILL_DESCRIPTION = (
    "Split shared expenses, calculate who owes whom, and record debt settlements. "
    "Use when the user says 'Split 1200 among four of us', 'Who owes what in Goa Trip?', "
    "'What are the balances in Roommates?', or 'Record settlement of 300 rupees from Bob to me'. "
    "Do not use for individual personal expenses; use expense_log instead."
)


@requires()
@idempotent(tool_name="split_bill")
@instrument_tool("split_bill", "finance")
async def split_bill(
    action: str,
    amount: str | int | None = None,
    currency: str = "INR",
    group: str | None = None,
    participants: list[str] | str | None = None,
    payer: str | None = "You",
    description: str | None = None,
    settle_from: str | None = None,
    settle_to: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Execute shared expense splitting, group balances, and settlements."""
    principal = get_current_principal()
    if principal is None or principal.anonymous or principal.user_id is None:
        raise AuthRequiredError(
            spoken="Please link your account in the Alexa app to split bills and track balances.",
            detail="Account linking required for split_bill tool",
        )

    try:
        req = SplitBillRequest(
            action=SplitBillAction(action.strip().lower()),
            amount=amount,
            currency=currency,
            group=group,
            participants=participants,
            payer=payer,
            description=description,
            settle_from=settle_from,
            settle_to=settle_to,
            request_id=request_id,
        )

        service = get_split_bill_service()
        data, spoken = await service.execute(user_id=principal.user_id, request=req)

        next_actions = ["split_bill(action='balances')", "split_bill(action='list_groups')"]
        if req.action == SplitBillAction.SPLIT and req.group:
            next_actions = [f"split_bill(action='balances', group='{req.group}')"]

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
        logger.exception("Unexpected error in split_bill tool: %s", exc)
        return fail(SahayakError(), module="finance", version="0.1.0")
