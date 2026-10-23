"""Schemas and response data models for local_info module (T12.1, T12.2)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DataSourceMetadata(BaseModel):
    """Structured attribution and freshness metadata for external data."""

    source_id: str = Field(..., description="Unique source identifier.")
    source_name: str = Field(..., description="Display name of the data provider.")
    license: str = Field(..., description="License terms governing data usage.")
    attribution: str = Field(..., description="Required source attribution.")
    as_of: str = Field(..., description="ISO timestamp representing data freshness.")
    is_stale: bool = Field(False, description="Whether data was served from stale fallback cache.")


class TransitStatusRequest(BaseModel):
    """Input payload for transit status and departures tool."""

    action: Literal["next_departures", "status"] = Field(
        "next_departures",
        description="Action to perform: 'next_departures' or 'status' for line health.",
    )
    station: str | None = Field(
        None,
        description="Station or stop name (e.g., 'Rajiv Chowk', 'cp', 'IGI Airport', 'Hauz Khas').",
    )
    line: str | None = Field(
        None,
        description="Transit line name or color (e.g., 'Yellow', 'Blue', 'Airport Express').",
    )
    destination: str | None = Field(
        None,
        description="Optional terminus or destination filter.",
    )
