"""
Circuit breaker middleware for upstream resilience.

Implements the circuit breaker pattern:
- CLOSED: Normal operation, requests flow through
- OPEN: Upstream is failing, requests are rejected immediately
- HALF_OPEN: Testing if upstream recovered, limited requests allowed
"""
from __future__ import annotations

import time

from src.core.config import GatewaySettings
from src.core.state import CircuitBreakerState, CircuitState


class CircuitBreakerError(Exception):
    """Raised when circuit is open for an upstream."""

    def __init__(self, upstream_name: str, retry_after: float) -> None:
        self.upstream_name = upstream_name
        self.retry_after = retry_after
        super().__init__(f"Circuit open for {upstream_name}")


async def check_circuit(
    cb: CircuitBreakerState,
    upstream_name: str,
    settings: GatewaySettings,
) -> None:
    """
    Check if the circuit allows a request through.
    Raises CircuitBreakerError if the circuit is open.
    """
    async with cb.lock:
        if cb.state == CircuitState.CLOSED:
            return

        if cb.state == CircuitState.OPEN:
            elapsed = time.monotonic() - cb.last_failure_time
            timeout = settings.circuit_breaker.recovery_timeout

            if elapsed >= timeout:
                # Transition to half-open
                cb.state = CircuitState.HALF_OPEN
                cb.half_open_calls = 0
            else:
                raise CircuitBreakerError(
                    upstream_name, timeout - elapsed
                )

        if cb.state == CircuitState.HALF_OPEN:
            if cb.half_open_calls >= settings.circuit_breaker.half_open_max_calls:
                raise CircuitBreakerError(upstream_name, 5.0)
            cb.half_open_calls += 1


async def record_success(cb: CircuitBreakerState) -> None:
    """Record a successful request — may close the circuit."""
    async with cb.lock:
        if cb.state == CircuitState.HALF_OPEN:
            cb.state = CircuitState.CLOSED
            cb.failure_count = 0
            cb.half_open_calls = 0
        elif cb.state == CircuitState.CLOSED:
            cb.failure_count = max(0, cb.failure_count - 1)


async def record_failure(
    cb: CircuitBreakerState,
    settings: GatewaySettings,
) -> None:
    """Record a failed request — may open the circuit."""
    async with cb.lock:
        cb.failure_count += 1
        cb.last_failure_time = time.monotonic()

        if cb.state == CircuitState.HALF_OPEN:
            # Immediately revert to open
            cb.state = CircuitState.OPEN
        elif cb.failure_count >= settings.circuit_breaker.failure_threshold:
            cb.state = CircuitState.OPEN
