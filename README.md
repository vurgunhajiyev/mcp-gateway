# MCP Gateway

Production-ready unified entry point for AI Agents and downstream APIs, implementing the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/).

---

## Quick Start (Local — 5 minutes)

### Prerequisites

| Tool | Minimum Version | Check |
|------|----------------|-------|
| Python | 3.10+ | `python3 --version` |
| pip | 23+ | `pip3 --version` |
| make | any | `make --version` |
| Docker *(optional)* | 24+ | `docker --version` |

> **macOS**: Install Python via [Homebrew](https://brew.sh): `brew install python@3.12`
> **Windows**: Install Python from [python.org](https://python.org), then use `make` via WSL or Git Bash.

---

### Option A — Run with Python directly (recommended for development)

```bash
# 1. Clone / open the project folder
cd mcp-gateway

# 2. One-command setup (creates virtualenv + installs deps + copies .env)
make setup

# 3. Start the gateway
make run
```

The gateway starts at **http://localhost:8080**.

Open the interactive API docs at **http://localhost:8080/docs**.

---

### Option B — Run with Docker Compose (full stack)

```bash
# Starts gateway + Redis + Prometheus + Grafana + Jaeger
make docker-up
```

| Service | URL |
|---------|-----|
| Gateway API | http://localhost:8080 |
| API Docs | http://localhost:8080/docs |
| Grafana | http://localhost:3000 (admin/admin) |
| Prometheus | http://localhost:9091 |
| Jaeger (traces) | http://localhost:16686 |

---

## Manual Setup (step by step)

If you prefer not to use `make`:

```bash
# 1. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate          # macOS/Linux
# .venv\Scripts\activate           # Windows

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Copy environment config
cp .env.example .env

# 4. Create log directory
mkdir -p logs

# 5. Start the gateway
uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload
```

---

## Configuration

All configuration is in the `.env` file (copied from `.env.example` during setup).

### Key settings

```dotenv
# Auth — who can call the gateway
GATEWAY_AUTH_ENABLED=true
GATEWAY_API_KEYS_FILE=config/api_keys.json      # your API keys

# Upstream APIs — what the gateway proxies to
GATEWAY_UPSTREAM_CONFIG_FILE=config/upstreams.json

# Rate limiting
GATEWAY_RATE_LIMIT__DEFAULT_RPM=60             # requests per minute per identity
GATEWAY_RATE_LIMIT__BURST_ALLOWANCE=10

# Debug / dev mode
GATEWAY_DEBUG=true
GATEWAY_ENVIRONMENT=development
```

### Add your own upstream API

Edit `config/upstreams.json`:

```json
[
  {
    "name": "my-api",
    "url": "https://api.example.com",
    "description": "My downstream API",
    "upstream_token": "your-bearer-token-here",
    "timeout_seconds": 30,
    "tags": ["internal"]
  }
]
```

### Add an API key

Edit `config/api_keys.json`:

```json
[
  {
    "key": "my-secret-key-001",
    "owner": "your-name",
    "allowed_upstreams": [],
    "rate_limit_rpm": -1,
    "scopes": ["read", "write"]
  }
]
```

---

## Try It Out

Once the gateway is running, open a new terminal and try these:

### Health check (no auth required)
```bash
curl http://localhost:8080/health
```

### List configured upstreams
```bash
curl http://localhost:8080/upstreams \
  -H "X-Api-Key: dev-key-alice-001"
```

### Send an MCP initialize request
```bash
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: dev-key-alice-001" \
  -d '{
    "version": "1.0",
    "request": {
      "jsonrpc": "2.0",
      "id": 1,
      "method": "initialize",
      "params": {
        "protocolVersion": "2024-11-05",
        "clientInfo": {"name": "my-agent", "version": "1.0"}
      }
    }
  }'
```

### Register an AI agent (get a session token)
```bash
curl -X POST http://localhost:8080/agents/register \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: dev-key-alice-001" \
  -d '{
    "agent_name": "my-llm-agent",
    "agent_version": "1.0.0",
    "requested_upstreams": [],
    "requested_scopes": ["read", "write"]
  }'
```

### Use agent token to call MCP
```bash
# Replace <token> with the token from the register response
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "X-Agent-Token: <token>" \
  -d '{
    "request": {
      "jsonrpc": "2.0",
      "id": 2,
      "method": "tools/list"
    }
  }'
```

### Proxy directly to an upstream
```bash
curl -X POST http://localhost:8080/mcp/notion \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: dev-key-alice-001" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

---

## Common Commands

```bash
make run           # Start gateway (http://localhost:8080)
make run-reload    # Start with hot-reload (auto-restarts on code change)
make test          # Run all tests
make test-unit     # Run unit tests only
make lint          # Lint code with ruff
make format        # Auto-format code
make typecheck     # Type check with mypy
make docker-up     # Start full stack (gateway + Redis + monitoring)
make docker-down   # Stop Docker stack
make clean         # Remove virtualenv and caches
```

---

## Project Structure

```
mcp-gateway/
├── src/
│   ├── main.py                    ← Entry point
│   ├── core/
│   │   ├── app.py                 ← App factory + middleware wiring
│   │   ├── config.py              ← All configuration (env + JSON)
│   │   └── state.py               ← Shared HTTP pool + rate buckets
│   ├── protocol/
│   │   ├── mcp_types.py           ← MCP message types
│   │   └── validator.py           ← Request validation pipeline
│   ├── routing/
│   │   ├── mcp_router.py          ← MCP method handling
│   │   └── proxy.py               ← Reverse proxy with retries
│   ├── security/
│   │   ├── auth.py                ← API Key + OAuth JWT + Agent auth
│   │   └── agent_registry.py      ← Agent session management
│   ├── middleware/
│   │   ├── rate_limiter.py        ← Token-bucket rate limiting
│   │   ├── logging_mw.py          ← Structured JSON access logs
│   │   └── circuit_breaker.py     ← Per-upstream circuit breaker
│   └── observability/
│       ├── telemetry.py           ← OpenTelemetry + Prometheus
│       └── health.py              ← /health, /readyz, /metrics
├── config/
│   ├── api_keys.json              ← API credentials
│   └── upstreams.json             ← Downstream API definitions
├── tests/
│   ├── unit/                      ← Fast, isolated tests
│   └── integration/               ← Full stack tests
├── deploy/k8s/                    ← Kubernetes manifests
├── monitoring/                    ← Prometheus + Grafana configs
├── Dockerfile                     ← Multi-stage production image
├── docker-compose.yml             ← Local dev stack
├── Makefile                       ← Developer commands
└── .env.example                   ← Config template
```

---

## Authentication

The gateway supports three auth methods, all tried in order on each request:

| Method | Header | Example |
|--------|--------|---------|
| API Key | `X-Api-Key` | `X-Api-Key: dev-key-alice-001` |
| Agent Token | `X-Agent-Token` | `X-Agent-Token: <jwt>` |
| OAuth Bearer | `Authorization` | `Authorization: Bearer <jwt>` |

Public paths (no auth needed): `/health`, `/readyz`, `/metrics`, `/docs`

---

## Key Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/health` | GET | None | Liveness probe |
| `/readyz` | GET | None | Readiness + upstream health |
| `/metrics` | GET | None | Prometheus metrics |
| `/docs` | GET | None | Swagger UI |
| `/mcp` | POST | Required | MCP protocol endpoint |
| `/mcp/{upstream}` | POST | Required | Direct upstream proxy |
| `/agents/register` | POST | Required | Register AI agent |
| `/agents/sessions` | GET | Required | List active sessions |
| `/upstreams` | GET | Required | List configured upstreams |
| `/config/info` | GET | Required | Gateway configuration info |

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'src'`**
→ Make sure you're in the `mcp-gateway/` directory, not a subdirectory.
→ Run `pip install -e ".[dev]"` from the project root.

**`401 Unauthorized`**
→ Add header `-H "X-Api-Key: dev-key-alice-001"` to your requests.
→ Check `config/api_keys.json` contains the key you're using.

**`Address already in use` (port 8080)**
→ Change the port: `uvicorn src.main:app --port 8090`
→ Or update `GATEWAY_PORT=8090` in your `.env` file.

**`429 Too Many Requests`**
→ You've hit the rate limit. Wait a minute or increase `GATEWAY_RATE_LIMIT__DEFAULT_RPM` in `.env`.

---

## Documentation

Full architecture document: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
