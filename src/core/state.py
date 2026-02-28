"""
Shared gateway state — manages HTTP client pool, rate-limit buckets,
circuit breaker states, and upstream resolution.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import httpx

from src.core.config import GatewaySettings, UpstreamServer


class AuthType(str, Enum):
    API_KEY = "api_key"
    OAUTH = "oauth"
    AGENT_TOKEN = "agent_token"
    ANONYMOUS = "anonymous"


@dataclass
class AuthContext:
    """Carries identity information through the request lifecycle."""

    authenticated: bool = False
    auth_type: AuthType = AuthType.ANONYMOUS
    owner: str = ""
    allowed_upstreams: list[str] = field(default_factory=list)
    rate_limit_rpm: int = -1
    scopes: list[str] = field(default_factory=list)
    tier: str = "standard"
    agent_id: str = ""  # for AI agent sessions
    metadata: dict = field(default_factory=dict)

    def can_access(self, upstream_name: str) -> bool:
        if not self.allowed_upstreams:
            return True  # empty = all upstreams
        return upstream_name in self.allowed_upstreams


@dataclass
class RateLimitBucket:
    """Token bucket state per identity."""

    tokens: float
    max_tokens: float
    refill_rate: float  # tokens per second
    last_refill: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def consume(self, count: float = 1.0) -> tuple[bool, float]:
        """Try to consume tokens. Returns (allowed, retry_after_seconds)."""
        async with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.max_tokens, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now

            if self.tokens >= count:
                self.tokens -= count
                return True, 0.0

            wait = (count - self.tokens) / self.refill_rate
            return False, wait


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerState:
    """Per-upstream circuit breaker state."""

    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0
    half_open_calls: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class GatewayState:
    """Singleton managing shared resources across the gateway."""

    def __init__(self, settings: GatewaySettings) -> None:
        self.settings = settings
        self._http_client: Optional[httpx.AsyncClient] = None
        self._rate_limit_buckets: dict[str, RateLimitBucket] = {}
        self._circuit_breakers: dict[str, CircuitBreakerState] = {}
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize shared resources on startup."""
        self._http_client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_keepalive_connections=20,
                max_connections=100,
                keepalive_expiry=30.0,
            ),
            timeout=httpx.Timeout(
                connect=self.settings.connect_timeout,
                read=self.settings.default_upstream_timeout,
                write=10.0,
                pool=5.0,
            ),
            follow_redirects=True,
            http2=True,
        )

        # Pre-initialize circuit breakers for configured upstreams
        for upstream in self.settings.upstreams:
            self._circuit_breakers[upstream.name] = CircuitBreakerState()

    async def shutdown(self) -> None:
        """Graceful shutdown of shared resources."""
        if self._http_client:
            await self._http_client.aclose()

    @property
    def http_client(self) -> httpx.AsyncClient:
        if not self._http_client:
            raise RuntimeError("Gateway state not initialized. Call initialize() first.")
        return self._http_client

    async def get_rate_limit_bucket(self, identity: str) -> RateLimitBucket:
        """Get or create a rate limit bucket for the given identity."""
        async with self._lock:
            if identity not in self._rate_limit_buckets:
                rpm = self.settings.rate_limit.default_rpm
                burst = self.settings.rate_limit.burst_allowance
                self._rate_limit_buckets[identity] = RateLimitBucket(
                    tokens=float(burst),
                    max_tokens=float(burst),
                    refill_rate=rpm / 60.0,
                )
            return self._rate_limit_buckets[identity]

    def get_circuit_breaker(self, upstream_name: str) -> CircuitBreakerState:
        """Get the circuit breaker for an upstream."""
        if upstream_name not in self._circuit_breakers:
            self._circuit_breakers[upstream_name] = CircuitBreakerState()
        return self._circuit_breakers[upstream_name]

    def resolve_upstream(self, name: str) -> Optional[UpstreamServer]:
        """Resolve an upstream by name."""
        for upstream in self.settings.upstreams:
            if upstream.name == name:
                return upstream
        return None

    def get_default_upstream(self) -> Optional[UpstreamServer]:
        """Return the first configured upstream as default."""
        return self.settings.upstreams[0] if self.settings.upstreams else None
