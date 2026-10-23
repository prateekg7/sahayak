"""Pydantic schemas for the home and family module (T9.2)."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class SharedListAction(StrEnum):
    """Supported operations for the shared_list MCP tool."""

    ADD = "add"
    REMOVE = "remove"
    READ = "read"
    CHECK_OFF = "check_off"
    CLEAR_CHECKED = "clear_checked"


class SharedListRequest(BaseModel):
    """Request model for the shared_list tool."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    action: SharedListAction = SharedListAction.READ
    household_id: str | None = None
    list_name: Annotated[str, Field(default="shopping", max_length=128)] = "shopping"
    item: Annotated[str | None, Field(default=None, max_length=128)] = None
    quantity: Annotated[str | None, Field(default=None, max_length=64)] = None
