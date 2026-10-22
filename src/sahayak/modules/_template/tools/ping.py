"""Ping tool implementation proving MCP wiring and envelope contract."""

from __future__ import annotations

from typing import Any

from sahayak.core.envelope import ok
from sahayak.modules._template.adapters.sample_repo import InMemoryPingRepository
from sahayak.modules._template.schemas import PingRequest, PingResponseData
from sahayak.modules._template.service.sample import TemplateService

_repo = InMemoryPingRepository()
_service = TemplateService(repo=_repo)

PING_ECHO_DESCRIPTION = (
    "Echoes back a test message to verify that the Sahayak MCP connection is healthy. "
    "Use when testing connectivity or confirming the server is online, "
    "e.g. 'Alexa, ask Sahayak to ping'. "
    "Do not use for academic quizzes, flashcards, or study plans."
)


async def ping_echo(message: str = "ping", request_id: str = "") -> dict[str, Any]:
    """Echo back the caller's message wrapped in a standardized envelope."""
    if request_id:
        from sahayak.core.request_id import set_request_id

        set_request_id(request_id)

    from sahayak.core.observability.instrumentation import instrument_tool

    async with instrument_tool("ping_echo", "_template"):
        req = PingRequest(message=message)
        echo_result = await _service.process_ping(req.message)
        data = PingResponseData(echo=echo_result, received_length=len(req.message)).model_dump()
        return ok(
            spoken_summary=f"Pong. {echo_result}",
            data=data,
            next_actions=["ping again with another message"],
            module="_template",
            version="0.1.0",
        )
