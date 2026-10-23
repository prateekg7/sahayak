"""Schemas and response data models for local_info module (T12.1)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DataSourceMetadata(BaseModel):
    """Structured attribution and freshness metadata for external data."""

    source_id: str = Field(..., description="Unique source identifier.")
    source_name: str = Field(..., description="Display name of the data provider.")
    license: str = Field(..., description="License terms governing data usage.")
    attribution: str = Field(..., description="Required source attribution.")
    as_of: str = Field(..., description="ISO timestamp representing data freshness.")
    is_stale: bool = Field(False, description="Whether data was served from stale fallback cache.")
