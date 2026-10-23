"""Pydantic schemas for the finance module (T6.1)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ExpenseAction(str, Enum):
    """Supported expense log actions."""

    ADD = "add"
    LIST = "list"
    UNDO_LAST = "undo_last"
    DELETE = "delete"


class ExpenseLogRequest(BaseModel):
    """Input payload for the 'expense_log' MCP tool."""

    action: ExpenseAction = Field(
        ...,
        description="Expense action: 'add', 'list', 'undo_last', or 'delete'.",
    )
    amount: str | int | None = Field(
        default=None,
        description="Monetary amount (e.g. 200, '200', '200.50'). Required for 'add'.",
    )
    currency: str = Field(
        default="INR",
        max_length=3,
        description="3-letter ISO currency code (e.g. 'INR', 'USD', 'EUR').",
    )
    category: str | None = Field(
        default=None,
        max_length=64,
        description="Expense category or note (e.g. 'groceries', 'dinner', 'cab').",
    )
    note: str | None = Field(
        default=None,
        max_length=255,
        description="Optional additional details or vendor name.",
    )
    expense_id: str | None = Field(
        default=None,
        description="Expense UUID (required for 'delete').",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Maximum entries to return for 'list'.",
    )
    request_id: str | None = Field(
        default=None,
        description="Optional idempotency key for mutations.",
    )


class ExpenseData(BaseModel):
    """Representation of an individual expense entry."""

    id: str
    user_id: str
    amount_minor: int
    currency: str
    category: str
    note: str | None = None
    occurred_at: str | None = None
    formatted_amount: str


class ExpenseResponseData(BaseModel):
    """Output payload for the 'expense_log' tool inside the standard envelope."""

    action: str
    expense: ExpenseData | None = None
    expenses: list[ExpenseData] = Field(default_factory=list)
    total_amount_minor: int = 0
    formatted_total: str = ""
    currency: str = "INR"
    count: int = 0
