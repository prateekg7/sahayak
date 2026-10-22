"""Observability foundation: structured logging, Prometheus metrics, and OpenTelemetry tracing."""

from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.core.observability.logging import configure_logging, get_logger
from sahayak.core.observability.metrics import (
    CACHE_HITS_TOTAL,
    CACHE_MISSES_TOTAL,
    LLM_DURATION_SECONDS,
    LLM_REQUESTS_TOTAL,
    LLM_TOKENS_TOTAL,
    TOOL_CALLS_TOTAL,
    TOOL_DURATION_SECONDS,
    render_metrics,
)
from sahayak.core.observability.redaction import redact_text, redact_value
from sahayak.core.observability.tracing import get_tracer

__all__ = [
    "CACHE_HITS_TOTAL",
    "CACHE_MISSES_TOTAL",
    "LLM_DURATION_SECONDS",
    "LLM_REQUESTS_TOTAL",
    "LLM_TOKENS_TOTAL",
    "TOOL_CALLS_TOTAL",
    "TOOL_DURATION_SECONDS",
    "configure_logging",
    "get_logger",
    "get_tracer",
    "instrument_tool",
    "redact_text",
    "redact_value",
    "render_metrics",
]
