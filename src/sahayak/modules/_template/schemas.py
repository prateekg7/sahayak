"""Pydantic schemas for the template module."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PingRequest(BaseModel):
    """Input payload for the ping tool."""

    message: str = Field(
        default="ping",
        max_length=100,
        description="The message text to echo back to the caller.",
    )


class PingResponseData(BaseModel):
    """Structured data returned by ping."""

    echo: str
    received_length: int
