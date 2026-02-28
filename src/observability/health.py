"""
Health check endpoints.

Provides:
- /health — lightweight liveness probe
- /readyz — full readiness probe with upstream health checks
- /metrics — Prometheus metrics endpoint
"""
from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import ORJSONResponse, PlainTextResponse
from prometheus_client import generate_latest

from src.core.state import CircuitState, GatewayState

router = APIRouter(tags=["Health"])


@router.get("/health")
async def liveness() -> dict[str, str]:
    """Simple liveness probe — always returns 200 if the process is running."""
    return {"status": "ok"}


@router.get("/readyz")
async def readiness(request: Request) -> ORJSONResponse:
    """
    Readiness probe — checks all upstream health endpoints.
    Returns 200 if all upstreams are healthy, 207 if degraded.
    """
    state: GatewayState = request.app.state.gateway
    results: dict[str, Any] = {}
    all_healthy = True

    for upstream in state.settings.upstreams:
        cb = state.get_circuit_breaker(upstream.name)
        health_url = f"{upstream.url.rstrip('/')}{upstream.health_check_path}"

        try:
            resp = await state.http_client.get(health_url, timeout=5.0)
            healthy = resp.status_code < 400
        except Exception:
            healthy = False

        results[upstream.name] = {
            "healthy": healthy,
            "circuit_state": cb.state.value,
            "url": upstream.url,
        }

        if not healthy:
            all_healthy = False

    status_code = 200 if all_healthy else 207
    return ORJSONResponse(
        content={
            "status": "healthy" if all_healthy else "degraded",
            "upstreams": results,
            "gateway_id": state.settings.gateway_id,
        },
        status_code=status_code,
    )


@router.get("/metrics")
async def prometheus_metrics() -> PlainTextResponse:
    """Prometheus metrics endpoint."""
    return PlainTextResponse(
        content=generate_latest().decode("utf-8"),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
