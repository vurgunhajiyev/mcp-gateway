"""
Application factory — creates and configures the FastAPI application.

Assembles:
- Middleware stack (Auth → Rate Limit → Logging)
- Route registration (MCP, Agents, Health)
- Lifespan management (startup/shutdown)
- Telemetry initialization
"""
from __future__ import annotations

import signal
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.agents.routes import router as agent_router
from src.core.config import GatewaySettings, get_settings
from src.core.state import GatewayState
from src.middleware.logging_mw import LoggingMiddleware
from src.middleware.rate_limiter import RateLimitMiddleware
from src.observability.health import router as health_router
from src.observability.telemetry import (
    instrument_fastapi,
    setup_logging,
    setup_telemetry,
)
from src.routing.mcp_router import router as mcp_router
from src.security.agent_registry import AgentRegistry
from src.security.auth import AuthMiddleware


def create_app(settings: GatewaySettings | None = None) -> FastAPI:
    """
    Application factory.

    Creates and fully configures the FastAPI application with:
    - All middleware layers
    - All route handlers
    - Lifespan hooks for resource management
    - Telemetry and observability
    """
    if settings is None:
        settings = get_settings()

    # Initialize logging and telemetry
    setup_logging(settings.observability)
    setup_telemetry(settings)

    app = FastAPI(
        title="MCP Gateway",
        description="Production-ready unified MCP gateway for AI agents and downstream APIs",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=_lifespan,
    )

    # Store settings for lifespan access
    app.state.settings = settings

    # ── CORS ──
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.debug else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Middleware stack (applied in reverse order) ──
    # Order: Request → Logging → RateLimit → Auth → Handler
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(AuthMiddleware)

    # ── Routes ──
    app.include_router(health_router)
    app.include_router(mcp_router)
    app.include_router(agent_router)

    # ── Management endpoints ──
    @app.get("/upstreams", tags=["Management"])
    async def list_upstreams() -> list[dict]:
        """List configured upstream servers."""
        return [
            {
                "name": u.name,
                "url": u.url,
                "description": u.description,
                "version": u.version,
                "tags": u.tags,
                "health_check_path": u.health_check_path,
            }
            for u in settings.upstreams
        ]

    @app.get("/config/info", tags=["Management"])
    async def config_info() -> dict:
        """Non-sensitive configuration info."""
        return {
            "gateway_id": settings.gateway_id,
            "environment": settings.environment.value,
            "api_version": settings.api_version,
            "supported_versions": settings.supported_versions,
            "auth_enabled": settings.auth_enabled,
            "rate_limit_enabled": settings.rate_limit.enabled,
            "upstream_count": len(settings.upstreams),
        }

    # Instrument for tracing
    instrument_fastapi(app)

    return app


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage startup and shutdown of shared resources."""
    settings: GatewaySettings = app.state.settings

    # Initialize gateway state
    gateway_state = GatewayState(settings)
    await gateway_state.initialize()
    app.state.gateway = gateway_state

    # Initialize agent registry
    app.state.agent_registry = AgentRegistry(settings)

    # Register graceful shutdown
    def _signal_handler(sig: int, frame: object) -> None:
        sys.exit(0)

    signal.signal(signal.SIGTERM, _signal_handler)

    yield

    # Shutdown
    await gateway_state.shutdown()
