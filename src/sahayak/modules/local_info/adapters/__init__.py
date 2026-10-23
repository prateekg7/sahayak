"""Adapters for local_info external data sources (T12.1)."""

from __future__ import annotations

__all__ = [
    "BaseHttpDataSource",
    "CircuitState",
    "DataSourceCircuitBreaker",
]

from sahayak.modules.local_info.adapters.base import BaseHttpDataSource
from sahayak.modules.local_info.adapters.circuit_breaker import (
    CircuitState,
    DataSourceCircuitBreaker,
)
