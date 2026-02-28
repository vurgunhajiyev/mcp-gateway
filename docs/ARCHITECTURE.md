# MCP Gateway — Architecture Document

## 1. High-Level Architecture

### 1.1 System Overview

The MCP Gateway is a production-ready unified entry point that sits between AI Agents (LLM-based systems) and downstream APIs. It implements the Model Context Protocol (MCP) as its native wire format while supporting standard REST/HTTP passthrough.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         AI Agents / Clients                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ Claude   │  │ GPT-4    │  │ Custom   │  │ REST Clients     │   │
│  │ Agent    │  │ Agent    │  │ LLM Agent│  │ (curl, Postman)  │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────────┬─────────┘   │
│       │              │              │                 │             │
│       └──────────────┴──────────────┴─────────────────┘             │
│                              │                                      │
│                    MCP Protocol / HTTPS                             │
└──────────────────────────────┼──────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        MCP GATEWAY                                   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                     Middleware Stack                          │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐  │    │
│  │  │ Logging  │→ │ Rate     │→ │ Auth     │→ │ Circuit    │  │    │
│  │  │ & Trace  │  │ Limiter  │  │ (JWT/Key)│  │ Breaker    │  │    │
│  │  └──────────┘  └──────────┘  └──────────┘  └────────────┘  │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                               │                                      │
│  ┌────────────────────────────┼──────────────────────────────────┐   │
│  │                    Protocol Layer                              │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐  │   │
│  │  │ MCP Envelope │  │ JSON-RPC 2.0 │  │ Method Validator   │  │   │
│  │  │ Parser       │  │ Validator    │  │ & Param Checker    │  │   │
│  │  └──────────────┘  └──────────────┘  └────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────┘│
│                               │                                      │
│  ┌────────────────────────────┼──────────────────────────────────┐   │
│  │                    Routing Layer                               │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐  │   │
│  │  │ Upstream     │  │ Proxy Engine │  │ Load Balancer      │  │   │
│  │  │ Resolver     │  │ (httpx h2)   │  │ (future)           │  │   │
│  │  └──────────────┘  └──────────────┘  └────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────┘│
│                               │                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                  Observability                                │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │    │
│  │  │OpenTelem │  │Prometheus│  │ Structlog│                   │    │
│  │  │ Tracing  │  │ Metrics  │  │ JSON     │                   │    │
│  │  └──────────┘  └──────────┘  └──────────┘                   │    │
│  └──────────────────────────────────────────────────────────────┘    │
└──────────────────────────────┼───────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      Downstream APIs (Upstreams)                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐    │
│  │ Notion   │  │ GitHub   │  │ Internal │  │ Any REST/MCP     │    │
│  │ MCP      │  │ API      │  │ Service  │  │ Server           │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

### 1.2 Component Breakdown

| Component | Module | Responsibility |
|-----------|--------|----------------|
| Gateway Core | `src/core/app.py` | App factory, lifespan, middleware assembly |
| Config | `src/core/config.py` | Pydantic settings, env/file loading |
| State | `src/core/state.py` | Shared state, HTTP pool, rate buckets |
| Auth Middleware | `src/security/auth.py` | API Key, OAuth JWT, Agent Token auth |
| Agent Registry | `src/security/agent_registry.py` | Agent registration, session management |
| Rate Limiter | `src/middleware/rate_limiter.py` | Token-bucket per identity |
| Circuit Breaker | `src/middleware/circuit_breaker.py` | Per-upstream failure protection |
| Logging | `src/middleware/logging_mw.py` | Structured JSON access logs |
| MCP Protocol | `src/protocol/mcp_types.py` | MCP type definitions, envelope format |
| Validator | `src/protocol/validator.py` | Full MCP request validation pipeline |
| MCP Router | `src/routing/mcp_router.py` | MCP method routing, gateway methods |
| Proxy | `src/routing/proxy.py` | HTTP reverse proxy with retries |
| Telemetry | `src/observability/telemetry.py` | OTel + Prometheus + structlog setup |
| Health | `src/observability/health.py` | Liveness, readiness, metrics endpoints |

### 1.3 Request Lifecycle

```
Client Request
     │
     ▼
[1] LoggingMiddleware — assigns request_id, starts timer
     │
     ▼
[2] RateLimitMiddleware — checks token bucket for identity
     │ (429 if exceeded)
     ▼
[3] AuthMiddleware — extracts credentials, populates AuthContext
     │ (401 if missing/invalid)
     ▼
[4] Route Matching — FastAPI router selects handler
     │
     ├── /health, /readyz, /metrics → Health endpoints
     ├── /agents/* → Agent management
     ├── /mcp → MCP protocol handler
     │    │
     │    ▼
     │   [5] Parse & validate MCP envelope
     │    │
     │    ▼
     │   [6] Route by MCP method:
     │        - initialize → return gateway capabilities
     │        - ping → echo
     │        - tools/list → aggregate from upstreams
     │        - tools/call, resources/* → proxy to upstream
     │    │
     │    ▼
     │   [7] Check circuit breaker state
     │    │
     │    ▼
     │   [8] Proxy to upstream with retry logic
     │    │
     │    ▼
     │   [9] Wrap upstream response in gateway envelope
     │
     └── /mcp/{upstream}/{path} → Direct proxy passthrough
```

### 1.4 Tech Stack Justification

**Python 3.12 + FastAPI** was chosen because:

- **Async-native**: FastAPI + uvicorn + httpx provide end-to-end async I/O, critical for a gateway that spends most time waiting on upstream responses.
- **MCP ecosystem alignment**: The MCP SDK and most MCP server implementations are Python-first. Using Python means the gateway can directly import and use MCP types.
- **Pydantic validation**: JSON-RPC 2.0 and MCP messages require rigorous schema validation. Pydantic v2 provides this with near-zero overhead.
- **Rapid iteration**: For a product that will evolve with the MCP spec, Python's development velocity beats Go/Rust for the protocol layer.
- **OpenTelemetry maturity**: Python's OTel instrumentation for FastAPI and httpx is production-grade.
- **HTTP/2 support**: httpx supports HTTP/2 natively, reducing connection overhead to upstreams.

For government-scale (>10K RPS), the architecture supports horizontal scaling via Kubernetes HPA. If single-node throughput becomes a bottleneck, critical hot paths (rate limiting, circuit breaker) can be offloaded to Redis/sidecar, and the gateway can be rewritten in Go using the same architecture.

---

## 2. MCP Protocol Handling

### 2.1 Gateway Envelope Format

The gateway wraps standard MCP JSON-RPC 2.0 messages in a routing envelope:

```json
{
  "version": "1.0",
  "agent_id": "agent_a1b2c3d4e5f6",
  "session_id": "sess_789xyz",
  "upstream": "notion",
  "api_version": "v1",
  "timestamp": "2026-02-26T12:00:00Z",
  "request": {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "search_pages",
      "arguments": {"query": "project roadmap"}
    }
  },
  "metadata": {
    "trace_id": "abc123"
  }
}
```

### 2.2 Gateway Response Format

```json
{
  "version": "1.0",
  "gateway_id": "mcp-gw-01",
  "session_id": "sess_789xyz",
  "upstream": "notion",
  "latency_ms": 142.5,
  "timestamp": "2026-02-26T12:00:00Z",
  "response": {
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
      "content": [
        {"type": "text", "text": "Found 3 matching pages..."}
      ]
    }
  },
  "metadata": {}
}
```

### 2.3 Validation Pipeline

```
Raw JSON → Envelope Validation → JSON-RPC Structure → Method Validation → Param Schema Check
```

Each step produces specific JSON-RPC error codes:
- `-32700`: Parse error (invalid JSON)
- `-32600`: Invalid request (missing fields)
- `-32601`: Method not found
- `-32602`: Invalid params

### 2.4 Upstream Routing Strategy

1. **Explicit routing**: Envelope `upstream` field specifies target.
2. **Path-based routing**: `/mcp/{upstream_name}/...` bypasses envelope.
3. **Default fallback**: First configured upstream if none specified.
4. **Access control**: AuthContext.can_access() gates upstream access per identity.

### 2.5 Agent Authentication Flow

```
Agent                          Gateway                         Upstream
  │                              │                               │
  │─── POST /agents/register ───▶│                               │
  │    {name, capabilities}      │                               │
  │                              │── Validate, issue JWT ──┐     │
  │◀── {agent_id, token} ───────│◀─────────────────────────┘     │
  │                              │                               │
  │─── POST /mcp ───────────────▶│                               │
  │    X-Agent-Token: <jwt>      │                               │
  │    {MCP envelope}            │── Validate JWT ──┐            │
  │                              │◀────────────────-┘            │
  │                              │── Proxy request ─────────────▶│
  │                              │◀── Response ─────────────────│
  │◀── {gateway envelope} ──────│                               │
```

---

## 3. Folder Structure

```
mcp-gateway/
├── src/
│   ├── __init__.py
│   ├── main.py                    # Entry point
│   ├── core/
│   │   ├── app.py                 # App factory, middleware assembly
│   │   ├── config.py              # Pydantic settings
│   │   └── state.py               # Shared state, HTTP pool
│   ├── protocol/
│   │   ├── mcp_types.py           # MCP type definitions
│   │   └── validator.py           # Request validation pipeline
│   ├── routing/
│   │   ├── mcp_router.py          # MCP method routing
│   │   └── proxy.py               # HTTP reverse proxy
│   ├── security/
│   │   ├── auth.py                # Auth middleware (JWT/Key/Agent)
│   │   └── agent_registry.py      # Agent session management
│   ├── middleware/
│   │   ├── rate_limiter.py        # Token-bucket rate limiting
│   │   ├── logging_mw.py          # Structured access logging
│   │   └── circuit_breaker.py     # Per-upstream circuit breaker
│   ├── observability/
│   │   ├── telemetry.py           # OTel + Prometheus setup
│   │   └── health.py              # Health/readiness/metrics
│   ├── agents/
│   │   └── routes.py              # Agent management API
│   ├── models/                    # Database models (future)
│   ├── schemas/                   # API schemas (future)
│   └── utils/                     # Shared utilities
├── config/
│   ├── api_keys.json              # API key credentials
│   └── upstreams.json             # Upstream server definitions
├── tests/
│   ├── unit/
│   │   ├── test_protocol.py
│   │   └── test_circuit_breaker.py
│   └── integration/
│       └── test_gateway.py
├── deploy/
│   ├── k8s/
│   │   ├── namespace.yml
│   │   ├── deployment.yml
│   │   ├── service.yml
│   │   ├── hpa.yml
│   │   ├── ingress.yml
│   │   └── pdb.yml
│   ├── helm/                      # Helm chart (future)
│   └── terraform/                 # IaC (future)
├── monitoring/
│   ├── prometheus/prometheus.yml
│   └── grafana/dashboards/
├── .github/workflows/ci.yml       # CI/CD pipeline
├── Dockerfile                     # Multi-stage production build
├── docker-compose.yml             # Local dev stack
├── pyproject.toml                 # Project config & dependencies
└── .env.example                   # Environment template
```

---

## 4. Non-Functional Requirements

### 4.1 Security Model

| Layer | Mechanism | Details |
|-------|-----------|---------|
| Transport | TLS 1.3 | Enforced at ingress/load balancer |
| API Keys | X-Api-Key header | Per-key scopes, upstream restrictions, rate limits |
| OAuth 2.0 | Bearer JWT | JWKS validation, OIDC provider integration |
| Agent Auth | X-Agent-Token | Gateway-issued JWT, 24h TTL, auto-revocation |
| Secrets | K8s Secrets / Vault | Never in code, env-injected at runtime |
| CORS | Configurable | Locked down in production, open in dev |
| Headers | Hop-by-hop stripping | Prevents header injection attacks |
| Non-root | UID 1001 | Docker container runs as unprivileged user |

### 4.2 Observability

**Distributed Tracing (OpenTelemetry)**:
- Every request gets a trace spanning gateway → upstream.
- Traces exported to Jaeger/Tempo via OTLP gRPC.
- Configurable sampling rate (1.0 in dev, 0.1 in prod).

**Metrics (Prometheus)**:
- `mcp_gateway_requests_total` — by method, path, status, auth_type, upstream
- `mcp_gateway_request_duration_seconds` — histogram with p50/p95/p99 buckets
- `mcp_gateway_upstream_errors_total` — by upstream and error type
- `mcp_gateway_circuit_breaker_state` — real-time circuit state per upstream
- `mcp_gateway_active_agent_sessions` — current agent count
- `mcp_gateway_rate_limit_rejections_total` — rate limit pressure

**Structured Logging (structlog)**:
- JSON format for log aggregation (ELK/Loki).
- Every log entry includes: request_id, method, path, status, latency_ms, auth_owner, agent_id.
- Log levels: INFO for success, WARNING for 4xx, ERROR for 5xx.

### 4.3 Rate Limiting Strategy

**Algorithm**: Token bucket per authenticated identity.

```
Identity = "{auth_type}:{owner}" or "agent:{agent_id}"

Bucket:
  max_tokens = burst_allowance (default: 10)
  refill_rate = RPM / 60 (default: 1 token/sec)

Per request:
  1. Refill tokens based on elapsed time
  2. If tokens >= 1: consume, allow request
  3. If tokens < 1: reject with 429 + Retry-After header
```

**Override hierarchy**: Per-key RPM > Per-JWT claim > Global default.

**Distributed mode**: Set `GATEWAY_RATE_LIMIT__REDIS_URL` to use Redis for cross-instance bucket synchronization.

### 4.4 Circuit Breaker / Retry Logic

**Circuit breaker** (per upstream):

```
CLOSED ──[N failures]──▶ OPEN ──[timeout]──▶ HALF_OPEN ──[success]──▶ CLOSED
                           ▲                      │
                           └──────[failure]────────┘
```

- Threshold: 5 consecutive failures → OPEN.
- Recovery: 60s timeout → HALF_OPEN (allow 3 probe requests).
- Success in HALF_OPEN → CLOSED. Failure → OPEN again.

**Retry logic** (per request):
- Max retries: 3 (configurable per upstream).
- Backoff: Exponential (0.5s, 1s, 2s, max 5s).
- Retryable: ConnectError, RemoteProtocolError, 502/503/504.
- Non-retryable: 4xx, timeout, circuit open.

---

## 5. Production Readiness

### 5.1 Docker

Multi-stage build: build wheel in builder stage, install in slim production image.
- Non-root user (UID 1001)
- Built-in healthcheck
- 4 uvicorn workers by default
- Separate ports for HTTP (8080) and metrics (9090)

### 5.2 CI/CD Pipeline

```
Push to branch
     │
     ├── Code Quality (ruff lint + format + mypy)
     │
     ├── Tests (pytest + coverage) [depends on Quality]
     │
     ├── Security Scan (safety + bandit) [depends on Quality]
     │
     └── Build & Push Docker (multi-arch) [depends on Test + Security]
              │
              ├── develop → Deploy Staging (auto)
              │
              └── release → Deploy Production (canary → full)
```

### 5.3 Kubernetes Scaling Strategy

**Horizontal Pod Autoscaler (HPA)**:
- Min replicas: 3 (HA baseline)
- Max replicas: 20
- Scale-up triggers: CPU > 70%, Memory > 80%, or custom metric > 100 RPS/pod
- Scale-up: +2 pods per 60s (fast response)
- Scale-down: -1 pod per 120s (conservative)
- Stabilization: 5 minutes before scale-down

**Pod Disruption Budget**: min 2 available at all times.

**Ingress**: NGINX with rate limiting (100 req/min at edge), TLS termination, and proxy timeouts.

**Anti-affinity**: Spread pods across nodes/zones for HA.

---

## 6. Product Strategy

### 6.1 Monetization Model

**Tier 1 — Open Source (Free)**:
- Core gateway with auth, rate limiting, logging
- Single-node deployment, in-memory state
- Community support

**Tier 2 — Pro ($49/mo per gateway instance)**:
- Redis-backed distributed rate limiting
- Advanced analytics dashboard (Grafana)
- SSO/SAML authentication
- Priority email support
- Webhook notifications

**Tier 3 — Enterprise ($499/mo or custom)**:
- Multi-region deployment with global load balancing
- Audit logging with compliance exports (SOC2, HIPAA)
- Custom SLAs (99.99% uptime)
- Role-based access control (RBAC) for gateway management
- Dedicated support + onboarding
- Air-gapped deployment option

**Tier 4 — Government ($Custom)**:
- FedRAMP compliance module
- On-premise deployment
- Hardware security module (HSM) integration
- Classified network support
- Dedicated infrastructure

### 6.2 Enterprise Features Roadmap

| Feature | Priority | Tier |
|---------|----------|------|
| Admin Dashboard (React) | P0 | Pro |
| Multi-tenant isolation | P0 | Enterprise |
| RBAC for gateway management | P0 | Enterprise |
| Audit log export (CSV/SIEM) | P1 | Enterprise |
| API versioning (v1/v2 coexistence) | P1 | Pro |
| Request/response transformation | P1 | Pro |
| WebSocket/SSE support for MCP streaming | P1 | Pro |
| GraphQL gateway mode | P2 | Enterprise |
| Plugin system (custom middleware) | P2 | Enterprise |
| Usage-based billing integration | P2 | Pro |
| Canary routing (% traffic split) | P2 | Enterprise |
| IP allowlisting / geo-fencing | P2 | Government |
| Data residency controls | P3 | Government |
| Mutual TLS (mTLS) between gateway and upstreams | P3 | Enterprise |

### 6.3 Competitive Positioning

This gateway differentiates from Kong/Traefik/AWS API Gateway by being **MCP-native**:
- First-class JSON-RPC 2.0 + MCP envelope support
- Built-in AI agent session management
- Tool/resource/prompt aggregation across multiple MCP servers
- Agent-aware rate limiting and access control
- Purpose-built for the emerging LLM agent ecosystem
