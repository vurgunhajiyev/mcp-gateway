"""
Structured logging middleware.

Emits JSON-formatted access logs with request tracing,
latency measurement, and authentication context.
"""
from __future__ import annotations

import time
import uuid

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from src.core.state import AuthContext

logger = structlog.get_logger("mcp_gateway.access")


class LoggingMiddleware(BaseHTTPMiddleware):
    """Structured access logging with request tracing."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("x-request-id", uuid.uuid4().hex[:8])
        start_time = time.perf_counter()

        # Attach request ID to response
        try:
            response = await call_next(request)
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            _log_request(request, 500, elapsed_ms, request_id)
            raise exc

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        response.headers["X-Request-Id"] = request_id
        response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.1f}"

        _log_request(request, response.status_code, elapsed_ms, request_id)

        return response


def _log_request(
    request: Request, status_code: int, latency_ms: float, request_id: str
) -> None:
    """Emit structured log entry."""
    auth: AuthContext = getattr(request.state, "auth", AuthContext())

    client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if not client_ip and request.client:
        client_ip = request.client.host

    log_data = {
        "request_id": request_id,
        "method": request.method,
        "path": str(request.url.path),
        "query": str(request.url.query) if request.url.query else None,
        "status": status_code,
        "latency_ms": round(latency_ms, 2),
        "client_ip": client_ip,
        "auth_type": auth.auth_type.value if auth.authenticated else None,
        "auth_owner": auth.owner if auth.authenticated else None,
        "agent_id": auth.agent_id if auth.agent_id else None,
        "user_agent": request.headers.get("user-agent", "")[:200],
    }

    if status_code >= 500:
        logger.error("request_completed", **log_data)
    elif status_code >= 400:
        logger.warning("request_completed", **log_data)
    else:
        logger.info("request_completed", **log_data)
