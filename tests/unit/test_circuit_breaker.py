"""Tests for circuit breaker logic."""
import pytest
import time

from src.core.config import GatewaySettings, CircuitBreakerConfig
from src.core.state import CircuitBreakerState, CircuitState
from src.middleware.circuit_breaker import (
    CircuitBreakerError,
    check_circuit,
    record_failure,
    record_success,
)


@pytest.fixture
def settings():
    return GatewaySettings(
        secret_key="test-secret",
        circuit_breaker=CircuitBreakerConfig(
            enabled=True,
            failure_threshold=3,
            recovery_timeout=1.0,
            half_open_max_calls=2,
        ),
    )


@pytest.fixture
def cb():
    return CircuitBreakerState()


@pytest.mark.asyncio
class TestCircuitBreaker:
    async def test_closed_allows_request(self, cb, settings):
        await check_circuit(cb, "test", settings)
        assert cb.state == CircuitState.CLOSED

    async def test_opens_after_threshold(self, cb, settings):
        for _ in range(3):
            await record_failure(cb, settings)
        assert cb.state == CircuitState.OPEN

    async def test_open_rejects_request(self, cb, settings):
        cb.state = CircuitState.OPEN
        cb.last_failure_time = time.monotonic()
        with pytest.raises(CircuitBreakerError):
            await check_circuit(cb, "test", settings)

    async def test_success_closes_half_open(self, cb, settings):
        cb.state = CircuitState.HALF_OPEN
        await record_success(cb)
        assert cb.state == CircuitState.CLOSED

    async def test_failure_reopens_half_open(self, cb, settings):
        cb.state = CircuitState.HALF_OPEN
        await record_failure(cb, settings)
        assert cb.state == CircuitState.OPEN
