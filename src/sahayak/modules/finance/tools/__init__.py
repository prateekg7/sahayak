"""MCP tools for the finance module."""

from __future__ import annotations

from sahayak.modules.finance.tools.budget import (
    BUDGET_DESCRIPTION,
    budget,
)
from sahayak.modules.finance.tools.expense_log import (
    EXPENSE_LOG_DESCRIPTION,
    expense_log,
)
from sahayak.modules.finance.tools.finance_report import (
    FINANCE_REPORT_DESCRIPTION,
    finance_report,
)
from sahayak.modules.finance.tools.split_bill import (
    SPLIT_BILL_DESCRIPTION,
    split_bill,
)

__all__ = [
    "BUDGET_DESCRIPTION",
    "EXPENSE_LOG_DESCRIPTION",
    "FINANCE_REPORT_DESCRIPTION",
    "SPLIT_BILL_DESCRIPTION",
    "budget",
    "expense_log",
    "finance_report",
    "split_bill",
]
