"""Circuit breaker implementation for protecting outbound provider calls."""

from __future__ import annotations

import enum
import time

from sahayak.shared.llm.ports import CircuitBreakerOpenError


class CircuitState(str, enum.Enum):
    """Current state of a provider circuit breaker."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Three-state circuit breaker per LLM provider.

    Transitions:
    - CLOSED -> OPEN when consecutive failures reach ``failure_threshold``.
    - OPEN -> HALF_OPEN when ``recovery_timeout_seconds`` has elapsed.
    - HALF_OPEN -> CLOSED on the first successful probe execution.
    - HALF_OPEN -> OPEN immediately on probe failure.
    """

    def __init__(
        self,
        provider: str,
        *,
        failure_threshold: int = 3,
        recovery_timeout_seconds: float = 30.0,
    ) -> None:
        self.provider = provider
        self.failure_threshold = max(1, failure_threshold)
        self.recovery_timeout_seconds = max(0.1, recovery_timeout_seconds)
        self._state: CircuitState = CircuitState.CLOSED
        self._consecutive_failures: int = 0
        self._opened_at: float = 0.0

    @property
    def state(self) -> CircuitState:
        """Return the current circuit state, checking for expiry if OPEN."""
        if (
            self._state == CircuitState.OPEN
            and time.monotonic() - self._opened_at >= self.recovery_timeout_seconds
        ):
            self._state = CircuitState.HALF_OPEN
        return self._state

    @property
    def consecutive_failures(self) -> int:
        """Number of consecutive failures recorded."""
        return self._consecutive_failures

    def can_execute(self) -> bool:
        """Check whether a call is permitted through the circuit.

        Raises:
            CircuitBreakerOpenError: If the circuit is currently OPEN.
        """
        current_state = self.state
        if current_state == CircuitState.OPEN:
            raise CircuitBreakerOpenError(self.provider)
        return True

    def record_success(self) -> None:
        """Record a successful provider call, resetting failures and closing circuit."""
        self._consecutive_failures = 0
        self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """Record a failed call. Trips to OPEN if threshold reached."""
        self._consecutive_failures += 1
        at_threshold = self._consecutive_failures >= self.failure_threshold
        if self._state == CircuitState.HALF_OPEN or at_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
