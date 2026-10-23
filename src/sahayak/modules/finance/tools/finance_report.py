"""The 'finance_report' MCP tool for periodic spending summaries and bill tracking (T6.4)."""

from __future__ import annotations

import logging
from typing import Any

from sahayak.core.auth.principal import get_current_principal, requires
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import AuthRequiredError, SahayakError
from sahayak.core.idempotency import idempotent
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.finance.schemas import (
    FinanceReportAction,
    FinanceReportRequest,
)
from sahayak.modules.finance.service.reports import FinanceReportService

logger = logging.getLogger(__name__)

_finance_report_service: FinanceReportService | None = None


def set_finance_report_service(service: FinanceReportService) -> None:
    """Inject the active FinanceReportService instance."""
    global _finance_report_service
    _finance_report_service = service


def get_finance_report_service() -> FinanceReportService:
    """Retrieve the injected FinanceReportService instance."""
    if _finance_report_service is None:
        raise RuntimeError("FinanceReportService has not been initialized.")
    return _finance_report_service


FINANCE_REPORT_DESCRIPTION = (
    "Generate spending summaries and track recurring bills or EMI due dates. "
    "Use when the user says 'Give me my monthly finance summary', "
    "'What did I spend on food this month?', 'What bills are due this week?', "
    "'Add electricity bill of 1500 due on day 25', or 'Mark my phone bill as paid'. "
    "Do not use for logging a single new expense; use expense_log instead."
)


@requires()
@idempotent(tool_name="finance_report")
@instrument_tool("finance_report", "finance")
async def finance_report(
    action: str = "summary",
    period: str = "monthly",
    currency: str = "INR",
    bill_id: str | None = None,
    bill_name: str | None = None,
    amount: str | int | None = None,
    due_day: int | None = None,
    frequency: str = "monthly",
    due_days_ahead: int = 7,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Execute finance reporting and bill tracking operations."""
    principal = get_current_principal()
    if principal is None or principal.anonymous or principal.user_id is None:
        raise AuthRequiredError(
            spoken=(
                "Please link your account in the Alexa app to view your "
                "financial reports and bills."
            ),
            detail="Account linking required for finance_report tool",
        )

    try:
        req = FinanceReportRequest(
            action=FinanceReportAction(action.strip().lower()),
            period=period,
            currency=currency,
            bill_id=bill_id,
            bill_name=bill_name,
            amount=amount,
            due_day=due_day,
            frequency=frequency,
            due_days_ahead=due_days_ahead,
            request_id=request_id,
        )

        service = get_finance_report_service()
        data, spoken = await service.execute(user_id=principal.user_id, request=req)

        next_actions = ["finance_report(action='summary')", "finance_report(action='bills_due')"]
        if req.action == FinanceReportAction.SUMMARY:
            next_actions = [
                f"finance_report(action='by_category', period='{req.period}')",
                "finance_report(action='bills_due')",
            ]
        elif req.action == FinanceReportAction.BILLS_DUE:
            next_actions = ["finance_report(action='summary')"]
        elif req.action in (FinanceReportAction.ADD_BILL, FinanceReportAction.MARK_BILL_PAID):
            next_actions = ["finance_report(action='bills_due')"]

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
        logger.exception("Unexpected error in finance_report tool: %s", exc)
        return fail(SahayakError(), module="finance", version="0.1.0")
