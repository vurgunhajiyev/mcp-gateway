# MCP Gateway — Developer Makefile
# Usage: make <target>

.PHONY: help setup install run test lint format typecheck clean docker-up docker-down

PYTHON  := python3
VENV    := .venv
PIP     := $(VENV)/bin/pip
PYTEST  := $(VENV)/bin/pytest
UVICORN := $(VENV)/bin/uvicorn
RUFF    := $(VENV)/bin/ruff
MYPY    := $(VENV)/bin/mypy

# ──────────────────────────
# Default target
# ──────────────────────────
help:
	@echo ""
	@echo "MCP Gateway — Available Commands"
	@echo "================================="
	@echo "  make setup       Create virtualenv and install all dependencies"
	@echo "  make run         Start the gateway (http://localhost:8080)"
	@echo "  make run-reload  Start with hot-reload (development mode)"
	@echo "  make test        Run all tests with coverage"
	@echo "  make test-unit   Run unit tests only"
	@echo "  make lint        Lint code with ruff"
	@echo "  make format      Auto-format code with ruff"
	@echo "  make typecheck   Type check with mypy"
	@echo "  make clean       Remove virtualenv and caches"
	@echo "  make docker-up   Start full stack with Docker Compose"
	@echo "  make docker-down Stop Docker Compose stack"
	@echo ""

# ──────────────────────────
# Setup
# ──────────────────────────
setup: $(VENV)/bin/activate

$(VENV)/bin/activate: pyproject.toml
	@echo ">>> Creating virtual environment..."
	$(PYTHON) -m venv $(VENV)
	@echo ">>> Installing dependencies..."
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	@cp -n .env.example .env 2>/dev/null || true
	@mkdir -p logs
	@echo ""
	@echo "✅  Setup complete. Run: make run"

install: $(VENV)/bin/activate

# ──────────────────────────
# Run
# ──────────────────────────
run: $(VENV)/bin/activate
	@echo ">>> Starting MCP Gateway on http://localhost:8080 ..."
	$(UVICORN) src.main:app --host 0.0.0.0 --port 8080

run-reload: $(VENV)/bin/activate
	@echo ">>> Starting MCP Gateway with hot-reload ..."
	$(UVICORN) src.main:app --host 0.0.0.0 --port 8080 --reload

# ──────────────────────────
# Tests
# ──────────────────────────
test: $(VENV)/bin/activate
	$(PYTEST) tests/ -v --tb=short

test-unit: $(VENV)/bin/activate
	$(PYTEST) tests/unit/ -v --tb=short

test-integration: $(VENV)/bin/activate
	$(PYTEST) tests/integration/ -v --tb=short

# ──────────────────────────
# Code Quality
# ──────────────────────────
lint: $(VENV)/bin/activate
	$(RUFF) check src/ tests/

format: $(VENV)/bin/activate
	$(RUFF) format src/ tests/

typecheck: $(VENV)/bin/activate
	$(MYPY) src/ --ignore-missing-imports

# ──────────────────────────
# Docker
# ──────────────────────────
docker-up:
	docker compose up -d
	@echo "Gateway:    http://localhost:8080"
	@echo "Grafana:    http://localhost:3000  (admin/admin)"
	@echo "Prometheus: http://localhost:9091"
	@echo "Jaeger:     http://localhost:16686"

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f gateway

# ──────────────────────────
# Cleanup
# ──────────────────────────
clean:
	rm -rf $(VENV) .pytest_cache .mypy_cache .ruff_cache __pycache__ htmlcov coverage.xml .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@echo "✅  Clean complete."
