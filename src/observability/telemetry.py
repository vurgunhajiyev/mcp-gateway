"""
OpenTelemetry and Prometheus observability setup.

Provides:
- Distributed tracing via OpenTelemetry
- Metrics via Prometheus
- Structured logging via structlog
"""
from __future__ import annotations

import structlog
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
from prometheus_client import Counter, Gauge, Histogram, Info

from src.core.config import GatewaySettings, ObservabilityConfig

# ──────────────────────────────────────────────
# Prometheus Metrics
# ──────────────────────────────────────────────

GATEWAY_INFO = Info("mcp_gateway", "MCP Gateway build information")

REQUEST_COUNT = Counter(
    "mcp_gateway_requests_total",
    "Total number of requests",
    ["method", "path", "status", "auth_type", "upstream"],
)

REQUEST_LATENCY = Histogram(
    "mcp_gateway_request_duration_seconds",
    "Request latency in seconds",
    ["method", "path", "upstream"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

ACTIVE_CONNECTIONS = Gauge(
    "mcp_gateway_active_connections",
    "Number of active connections",
)

UPSTREAM_ERRORS = Counter(
    "mcp_gateway_upstream_errors_total",
    "Total upstream errors by type",
    ["upstream", "error_type"],
)

CIRCUIT_BREAKER_STATE = Gauge(
    "mcp_gateway_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half_open)",
    ["upstream"],
)

RATE_LIMIT_REJECTIONS = Counter(
    "mcp_gateway_rate_limit_rejections_total",
    "Total rate-limited requests",
    ["identity", "tier"],
)

AGENT_SESSIONS = Gauge(
    "mcp_gateway_active_agent_sessions",
    "Number of active agent sessions",
)

MCP_METHOD_COUNT = Counter(
    "mcp_gateway_mcp_methods_total",
    "MCP method invocation count",
    ["method", "upstream"],
)


# ──────────────────────────────────────────────
# OpenTelemetry Setup
# ──────────────────────────────────────────────

def setup_telemetry(settings: GatewaySettings) -> None:
    """Initialize OpenTelemetry tracing and instrumentation."""
    obs = settings.observability

    resource = Resource.create({
        SERVICE_NAME: obs.service_name,
        "service.version": "1.0.0",
        "deployment.environment": settings.environment.value,
        "gateway.id": settings.gateway_id,
    })

    sampler = TraceIdRatioBased(obs.trace_sample_rate)
    provider = TracerProvider(resource=resource, sampler=sampler)

    if obs.otlp_endpoint:
        exporter = OTLPSpanExporter(endpoint=obs.otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)

    # Instrument httpx for outbound tracing
    HTTPXClientInstrumentor().instrument()

    GATEWAY_INFO.info({
        "version": "1.0.0",
        "environment": settings.environment.value,
        "gateway_id": settings.gateway_id,
    })


def instrument_fastapi(app: object) -> None:
    """Instrument FastAPI app for automatic tracing."""
    FastAPIInstrumentor.instrument_app(app)  # type: ignore


# ──────────────────────────────────────────────
# Structured Logging Setup
# ──────────────────────────────────────────────

def setup_logging(config: ObservabilityConfig) -> None:
    """Configure structlog for structured JSON logging."""
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if config.log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            _log_level_to_int(config.log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _log_level_to_int(level: str) -> int:
    """Convert log level string to integer."""
    levels = {
        "DEBUG": 10,
        "INFO": 20,
        "WARNING": 30,
        "ERROR": 40,
        "CRITICAL": 50,
    }
    return levels.get(level.upper(), 20)
