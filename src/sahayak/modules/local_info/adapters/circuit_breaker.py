"""Circuit breaker for protecting outbound external data source calls (T12.1)."""

from __future__ import annotations

import enum
import time


class CircuitState(str, enum.Enum):
    """Current state of a data source circuit breaker."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class DataSourceCircuitBreaker:
    """Circuit breaker for external data sources to prevent cascading failures.

    Transitions:
    - CLOSED -> OPEN when consecutive failures reach failure_threshold.
    - OPEN -> HALF_OPEN when recovery_timeout_seconds has elapsed.
    - HALF_OPEN -> CLOSED on successful execution.
    - HALF_OPEN -> OPEN immediately on probe failure.
    """

    def __init__(
        self,
        source_id: str,
        *,
        failure_threshold: int = 3,
        recovery_timeout_seconds: float = 30.0,
    ) -> None:
        self.source_id = source_id
        self.failure_threshold = max(1, failure_threshold)
        self.recovery_timeout_seconds = max(0.1, recovery_timeout_seconds)
        self._state: CircuitState = CircuitState.CLOSED
        self._consecutive_failures: int = 0
        self._opened_at: float = 0.0

    @property
    def state(self) -> CircuitState:
        """Return the current circuit state, transitioning to HALF_OPEN if recovery time passed."""
        if (
            self._state == CircuitState.OPEN
            and time.monotonic() - self._opened_at >= self.recovery_timeout_seconds
        ):
            self._state = CircuitState.HALF_OPEN
        return self._state

    @property
    def is_open(self) -> bool:
        """Check if circuit is currently OPEN (blocking calls)."""
        return self.state == CircuitState.OPEN

    @property
    def consecutive_failures(self) -> int:
        """Number of consecutive failures recorded."""
        return self._consecutive_failures

    def record_success(self) -> None:
        """Record successful call, closing circuit and resetting failures."""
        self._consecutive_failures = 0
        self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """Record a failed call. Trips circuit to OPEN if threshold reached."""
        self._consecutive_failures += 1
        at_threshold = self._consecutive_failures >= self.failure_threshold
        if self._state == CircuitState.HALF_OPEN or at_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
