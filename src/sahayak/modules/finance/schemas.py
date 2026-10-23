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


class BudgetAction(str, Enum):
    """Supported category budget actions (T6.2)."""

    SET = "set"
    STATUS = "status"
    LIST = "list"
    REMOVE = "remove"


class BudgetRequest(BaseModel):
    """Input payload for the 'budget' MCP tool."""

    action: BudgetAction = Field(
        ...,
        description="Budget action: 'set', 'status', 'list', or 'remove'.",
    )
    category: str | None = Field(
        default=None,
        max_length=64,
        description="Budget category (e.g. 'groceries', 'dining', 'shopping').",
    )
    amount: str | int | None = Field(
        default=None,
        description="Monthly budget cap amount (e.g. 5000, '5000'). Required for 'set'.",
    )
    currency: str = Field(
        default="INR",
        max_length=3,
        description="3-letter ISO currency code (default 'INR').",
    )
    timezone: str | None = Field(
        default=None,
        max_length=64,
        description="User timezone (e.g. 'Asia/Kolkata', 'America/New_York').",
    )
    request_id: str | None = Field(
        default=None,
        description="Optional idempotency key for mutations.",
    )


class BudgetData(BaseModel):
    """Representation of an individual category budget configuration."""

    id: str
    category: str
    amount_minor: int
    currency: str
    formatted_amount: str
    is_active: bool


class BudgetStatusData(BaseModel):
    """Calculated spending status and run-rate analysis for a budget."""

    category: str
    currency: str
    budget_minor: int
    spent_minor: int
    remaining_minor: int
    formatted_budget: str
    formatted_spent: str
    formatted_remaining: str
    is_overspent: bool
    percentage_used: float
    projected_overspend_minor: int
    threshold_crossed: str | None = None
    days_remaining: int


class BudgetResponseData(BaseModel):
    """Output payload for the 'budget' tool inside the standard envelope."""

    action: str
    budget: BudgetData | None = None
    status: BudgetStatusData | None = None
    budgets: list[BudgetStatusData] = Field(default_factory=list)
    count: int = 0


class SplitBillAction(str, Enum):
    """Supported bill splitting actions (T6.3)."""

    SPLIT = "split"
    BALANCES = "balances"
    SETTLE = "settle"
    LIST_GROUPS = "list_groups"
    CREATE_GROUP = "create_group"


class SplitBillRequest(BaseModel):
    """Input payload for the 'split_bill' MCP tool."""

    action: SplitBillAction = Field(
        ...,
        description="Action: 'split', 'balances', 'settle', 'list_groups', or 'create_group'.",
    )
    amount: str | int | None = Field(
        default=None,
        description="Total bill amount (e.g. 1200, '1200.50'). Required for 'split' and 'settle'.",
    )
    currency: str = Field(
        default="INR",
        max_length=3,
        description="3-letter ISO currency code (default 'INR').",
    )
    group: str | None = Field(
        default=None,
        max_length=128,
        description="Name of the group (e.g. 'Goa Trip', 'Roommates').",
    )
    participants: list[str] | str | None = Field(
        default=None,
        description="Names of people splitting (e.g. ['Alice', 'Bob'] or 'Alice, Bob').",
    )

    payer: str | None = Field(
        default="You",
        max_length=64,
        description="Name of person who paid the bill (defaults to 'You').",
    )
    description: str | None = Field(
        default=None,
        max_length=255,
        description="Description of the expense (e.g. 'Dinner at Olive', 'Cab fare').",
    )
    settle_from: str | None = Field(
        default=None,
        max_length=64,
        description="Person paying the settlement (required for 'settle').",
    )
    settle_to: str | None = Field(
        default=None,
        max_length=64,
        description="Person receiving the settlement (required for 'settle').",
    )
    request_id: str | None = Field(
        default=None,
        description="Optional idempotency key for mutations.",
    )


class ParticipantShareData(BaseModel):
    name: str
    amount_minor: int
    formatted_amount: str


class NetBalanceData(BaseModel):
    name: str
    net_minor: int
    formatted_net: str


class SettlementTransferData(BaseModel):
    from_name: str
    to_name: str
    amount_minor: int
    formatted_amount: str


class GroupSummaryData(BaseModel):
    id: str
    name: str
    currency: str
    members: list[str] = Field(default_factory=list)


class SplitBillResponseData(BaseModel):
    """Output payload for the 'split_bill' tool inside the standard envelope."""

    action: str
    group_name: str | None = None
    total_minor: int | None = None
    currency: str = "INR"
    shares: list[ParticipantShareData] = Field(default_factory=list)
    balances: list[NetBalanceData] = Field(default_factory=list)
    transfers: list[SettlementTransferData] = Field(default_factory=list)
    groups: list[GroupSummaryData] = Field(default_factory=list)
    count: int = 0
