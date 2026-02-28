"""
Rate limiting middleware.

Implements token-bucket rate limiting per authenticated identity.
Supports per-key overrides, burst allowance, and standard rate limit headers.
"""
from __future__ import annotations

import math

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from src.core.state import AuthContext, GatewayState

EXEMPT_PATHS = frozenset({"/health", "/readyz", "/docs", "/redoc", "/openapi.json", "/metrics"})


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token-bucket rate limiting per identity."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        state: GatewayState = request.app.state.gateway

        if not state.settings.rate_limit.enabled:
            return await call_next(request)

        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        auth: AuthContext = getattr(request.state, "auth", AuthContext())
        if not auth.authenticated:
            return await call_next(request)

        # Determine identity and per-key RPM override
        identity = f"{auth.auth_type.value}:{auth.owner}"
        if auth.agent_id:
            identity = f"agent:{auth.agent_id}"

        bucket = await state.get_rate_limit_bucket(identity)

        # Apply per-key override if set
        if auth.rate_limit_rpm > 0:
            bucket.refill_rate = auth.rate_limit_rpm / 60.0
            bucket.max_tokens = float(state.settings.rate_limit.burst_allowance)

        allowed, retry_after = await bucket.consume()

        if not allowed:
            return Response(
                content='{"error":"rate_limit_exceeded","message":"Too many requests"}',
                status_code=429,
                media_type="application/json",
                headers={
                    "Retry-After": str(math.ceil(retry_after)),
                    "X-RateLimit-Limit": str(int(bucket.refill_rate * 60)),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(math.ceil(retry_after)),
                },
            )

        response = await call_next(request)

        # Add rate limit info headers
        remaining = max(0, int(bucket.tokens))
        response.headers["X-RateLimit-Limit"] = str(int(bucket.refill_rate * 60))
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Policy"] = f"{int(bucket.refill_rate * 60)};w=60"

        return response
