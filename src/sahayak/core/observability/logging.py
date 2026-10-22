"""Structured JSON logging configuration with request-id and redaction."""

from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

from sahayak.core.observability.redaction import redaction_processor
from sahayak.core.request_id import get_request_id


def add_request_id(
    _logger: Any,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Inject the active request correlation ID into the log event."""
    request_id = get_request_id()
    if request_id:
        event_dict.setdefault("request_id", request_id)
    return event_dict


def configure_logging(*, json_output: bool = True) -> None:
    """Initialize structlog with standard processors and redaction.

    Args:
        json_output: Whether to render logs as compact JSON strings.
    """
    renderer: structlog.types.Processor
    if json_output:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        add_request_id,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        redaction_processor,
        structlog.processors.StackInfoRenderer(),
        renderer,
    ]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Bridge standard library logging to structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )


def get_logger(name: str | None = None) -> Any:
    """Return a structlog bound logger instance."""
    return structlog.get_logger(name)
