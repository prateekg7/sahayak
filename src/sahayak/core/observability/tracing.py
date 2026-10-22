"""OpenTelemetry tracing setup and tracer provider."""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.trace import Tracer

_tracer_provider = trace.get_tracer_provider()


def get_tracer(name: str = "sahayak") -> Tracer:
    """Return an OpenTelemetry Tracer instance for instrumenting code blocks."""
    return trace.get_tracer(name)
