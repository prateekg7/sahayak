"""Tool-call instrumentation wrapper recording traces, metrics, and structured logs."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sahayak.core.observability.logging import get_logger
from sahayak.core.observability.metrics import TOOL_CALLS_TOTAL, TOOL_DURATION_SECONDS
from sahayak.core.observability.tracing import get_tracer
from sahayak.core.request_id import get_request_id

logger = get_logger("sahayak.tools")
tracer = get_tracer("sahayak.tools")


@asynccontextmanager
async def instrument_tool(
    tool_name: str,
    module_name: str,
) -> AsyncIterator[None]:
    """Instrument an MCP tool invocation with tracing, metrics, and structured logs.

    Args:
        tool_name: Name of the tool being executed (e.g., 'ping_echo').
        module_name: Name of the owning module (e.g., '_template').

    Yields:
        None when inside the tool execution block.
    """
    request_id = get_request_id() or "unknown"
    start_time = time.monotonic()
    outcome = "success"

    with tracer.start_as_current_span(
        f"tool:{tool_name}",
        attributes={
            "tool": tool_name,
            "module": module_name,
            "request_id": request_id,
        },
    ) as span:
        try:
            yield
        except Exception as exc:
            outcome = "error"
            span.record_exception(exc)
            span.set_attribute("error", True)
            raise
        finally:
            duration_seconds = time.monotonic() - start_time
            latency_ms = round(duration_seconds * 1000, 2)

            # Record Prometheus metrics
            TOOL_CALLS_TOTAL.labels(
                tool=tool_name,
                module=module_name,
                outcome=outcome,
            ).inc()
            TOOL_DURATION_SECONDS.labels(
                tool=tool_name,
                module=module_name,
            ).observe(duration_seconds)

            # Emit structured log
            logger.info(
                "tool_call_completed",
                tool=tool_name,
                module=module_name,
                outcome=outcome,
                latency_ms=latency_ms,
                request_id=request_id,
            )
