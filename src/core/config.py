"""
Gateway configuration management.

Loads settings from environment variables, .env files, and JSON config files.
Supports three tiers: OAuth, API Keys, and Upstream Servers.
"""
from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class OAuthConfig(BaseModel):
    """OIDC / OAuth 2.0 provider configuration."""

    enabled: bool = False
    jwks_uri: str = ""
    issuer: str = ""
    audience: str = "mcp-gateway"
    algorithms: list[str] = Field(default_factory=lambda: ["RS256", "ES256"])
    jwks_cache_ttl: int = 3600  # seconds
    insecure_skip_verify: bool = False  # dev only — skips JWT signature check


class ApiKeyEntry(BaseModel):
    """A single API key credential with permissions."""

    key: str
    owner: str
    description: str = ""
    allowed_upstreams: list[str] = Field(default_factory=list)  # empty = all
    rate_limit_rpm: int = -1  # -1 = use global default
    scopes: list[str] = Field(default_factory=lambda: ["read", "write"])
    tier: str = "standard"  # standard, premium, enterprise


class UpstreamServer(BaseModel):
    """Downstream API server that the gateway proxies to."""

    name: str
    url: str
    description: str = ""
    version: str = "v1"
    timeout_seconds: float = 30.0
    connect_timeout: float = 5.0
    upstream_token: str = ""  # static bearer token for upstream auth
    tags: list[str] = Field(default_factory=list)
    health_check_path: str = "/health"
    max_retries: int = 3
    circuit_breaker_threshold: int = 5  # failures before opening circuit
    circuit_breaker_timeout: float = 60.0  # seconds before half-open


class RateLimitConfig(BaseModel):
    """Rate limiting configuration."""

    enabled: bool = True
    default_rpm: int = 60
    burst_allowance: int = 10
    strategy: str = "token_bucket"  # token_bucket | sliding_window | fixed_window
    redis_url: str = ""  # empty = in-memory; set for distributed limiting
    sync_interval_ms: int = 1000


class CircuitBreakerConfig(BaseModel):
    """Global circuit breaker defaults."""

    enabled: bool = True
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    half_open_max_calls: int = 3


class ObservabilityConfig(BaseModel):
    """Telemetry and monitoring configuration."""

    otlp_endpoint: str = ""
    otlp_protocol: str = "grpc"  # grpc | http
    service_name: str = "mcp-gateway"
    prometheus_enabled: bool = True
    prometheus_port: int = 9090
    log_level: str = "INFO"
    log_format: str = "json"  # json | text
    log_file: str = ""
    trace_sample_rate: float = 1.0  # 0.0 to 1.0


class GatewaySettings(BaseSettings):
    """Top-level gateway configuration loaded from env + files."""

    model_config = SettingsConfigDict(
        env_prefix="GATEWAY_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- General ---
    environment: Environment = Environment.DEVELOPMENT
    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = False
    workers: int = 1
    gateway_id: str = "mcp-gw-01"

    # --- Auth ---
    auth_enabled: bool = True
    secret_key: str = ""
    oauth: OAuthConfig = Field(default_factory=OAuthConfig)
    api_keys: list[ApiKeyEntry] = Field(default_factory=list)
    api_keys_file: str = ""

    # --- Upstreams ---
    upstreams: list[UpstreamServer] = Field(default_factory=list)
    upstream_config_file: str = ""
    default_upstream_timeout: float = 30.0
    connect_timeout: float = 5.0

    # --- Rate Limiting ---
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)

    # --- Circuit Breaker ---
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)

    # --- Observability ---
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)

    # --- Versioning ---
    api_version: str = "v1"
    supported_versions: list[str] = Field(default_factory=lambda: ["v1"])

    @model_validator(mode="after")
    def load_external_configs(self) -> "GatewaySettings":
        """Load API keys and upstream configs from JSON files if specified."""
        if self.api_keys_file and not self.api_keys:
            self.api_keys = _load_json_list(self.api_keys_file, ApiKeyEntry)
        if self.upstream_config_file and not self.upstreams:
            self.upstreams = _load_json_list(self.upstream_config_file, UpstreamServer)

        # Generate a dev secret key if none provided in non-production
        if not self.secret_key:
            if self.environment == Environment.PRODUCTION:
                raise ValueError("SECRET_KEY is required in production")
            self.secret_key = "dev-insecure-secret-key-change-me"

        return self


def _load_json_list(filepath: str, model: type[BaseModel]) -> list[Any]:
    """Load a JSON array file and parse each item into the given model."""
    path = Path(filepath)
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"Expected JSON array in {filepath}")
    return [model.model_validate(item) for item in raw]


def get_settings() -> GatewaySettings:
    """Factory function to create settings. Cached at module level for reuse."""
    return GatewaySettings()
