"""Pydantic schemas for the business orders tool (T10.1)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class OrderAction(str, Enum):
    """Supported actions for the orders MCP tool."""

    CREATE = "create"
    LIST_PENDING = "list_pending"
    UPDATE_STATUS = "update_status"
    GET = "get"


class OrderItemInput(BaseModel):
    """Input line item for creating an order."""

    item_name: str = Field(..., min_length=1, max_length=128)
    quantity: int = Field(default=1, ge=1, le=1000)
    unit_price_minor: int | None = Field(default=None, ge=0)
    unit_price: float | None = Field(default=None, ge=0)

    @model_validator(mode="before")
    @classmethod
    def resolve_minor_units(cls, values: Any) -> Any:
        if (
            isinstance(values, dict)
            and values.get("unit_price_minor") is None
            and values.get("unit_price") is not None
        ):
            val = float(values["unit_price"])
            values["unit_price_minor"] = int(round(val * 100))
        return values


class OrderRequest(BaseModel):
    """Request model for the orders MCP tool."""

    action: OrderAction = Field(default=OrderAction.LIST_PENDING)
    business_id: str | None = Field(default=None, max_length=64)
    order_number: int | None = Field(default=None, ge=1)
    customer_name: str | None = Field(default=None, max_length=128)
    items: list[OrderItemInput] | None = Field(default=None)
    status: str | None = Field(default=None, max_length=32)
    notes: str | None = Field(default=None, max_length=512)
    request_id: str | None = Field(default=None, max_length=64)
