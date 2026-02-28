"""
Authentication middleware.

Supports three auth strategies:
1. API Key — via X-Api-Key header or ?api_key= query param
2. OAuth 2.0 Bearer JWT — via Authorization: Bearer header
3. Agent Token — via X-Agent-Token header (for AI agent sessions)

Populates AuthContext on request state for downstream middleware.
"""
from __future__ import annotations

import time
from typing import Any, Optional

import httpx
import jwt
from cachetools import TTLCache
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from src.core.config import ApiKeyEntry, GatewaySettings, OAuthConfig
from src.core.state import AuthContext, AuthType, GatewayState

# JWKS cache: caches up to 10 providers, 1-hour TTL
_jwks_cache: TTLCache[str, dict[str, Any]] = TTLCache(maxsize=10, ttl=3600)


PUBLIC_PATHS = frozenset({"/health", "/readyz", "/docs", "/redoc", "/openapi.json", "/metrics"})


class AuthMiddleware(BaseHTTPMiddleware):
    """Extracts and validates credentials, populates AuthContext."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        state: GatewayState = request.app.state.gateway
        settings = state.settings

        # Skip auth for public paths
        if request.url.path in PUBLIC_PATHS:
            request.state.auth = AuthContext(authenticated=False)
            return await call_next(request)

        # Skip auth if disabled
        if not settings.auth_enabled:
            request.state.auth = AuthContext(
                authenticated=True,
                auth_type=AuthType.ANONYMOUS,
                owner="anonymous",
            )
            return await call_next(request)

        auth_ctx = await _extract_auth(request, settings)

        if auth_ctx is None:
            return Response(
                content='{"error":"authentication_required","message":"Provide X-Api-Key, Authorization Bearer, or X-Agent-Token header"}',
                status_code=401,
                media_type="application/json",
                headers={"WWW-Authenticate": 'Bearer realm="mcp-gateway"'},
            )

        request.state.auth = auth_ctx
        return await call_next(request)


async def _extract_auth(request: Request, settings: GatewaySettings) -> Optional[AuthContext]:
    """Try each auth strategy in order."""

    # 1. API Key
    api_key = request.headers.get("x-api-key") or request.query_params.get("api_key")
    if api_key:
        return _auth_api_key(api_key, settings)

    # 2. Agent Token (AI agent sessions)
    agent_token = request.headers.get("x-agent-token")
    if agent_token:
        return await _auth_agent_token(agent_token, settings)

    # 3. OAuth Bearer
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        return await _auth_oauth(token, settings)

    return None


def _auth_api_key(key: str, settings: GatewaySettings) -> Optional[AuthContext]:
    """Validate an API key against configured keys."""
    for entry in settings.api_keys:
        if entry.key == key:
            return AuthContext(
                authenticated=True,
                auth_type=AuthType.API_KEY,
                owner=entry.owner,
                allowed_upstreams=entry.allowed_upstreams,
                rate_limit_rpm=entry.rate_limit_rpm,
                scopes=entry.scopes,
                tier=entry.tier,
            )
    return None


async def _auth_oauth(token: str, settings: GatewaySettings) -> Optional[AuthContext]:
    """Validate a JWT bearer token using OIDC provider JWKS."""
    oauth = settings.oauth
    if not oauth.enabled:
        return None

    try:
        if oauth.insecure_skip_verify:
            # Dev mode: decode without verification
            claims = jwt.decode(token, options={"verify_signature": False})
        else:
            jwks = await _fetch_jwks(oauth)
            signing_key = _get_signing_key(jwks, token)
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=oauth.algorithms,
                issuer=oauth.issuer,
                audience=oauth.audience,
            )

        return AuthContext(
            authenticated=True,
            auth_type=AuthType.OAUTH,
            owner=claims.get("sub", "unknown"),
            allowed_upstreams=claims.get("mcp_upstreams", []),
            rate_limit_rpm=claims.get("mcp_rate_limit_rpm", -1),
            scopes=claims.get("scope", "").split(),
            tier=claims.get("mcp_tier", "standard"),
            metadata={"jwt_claims": claims},
        )
    except jwt.PyJWTError:
        return None


async def _auth_agent_token(token: str, settings: GatewaySettings) -> Optional[AuthContext]:
    """
    Validate an AI agent session token.
    Agent tokens are JWTs signed with the gateway's secret key,
    issued by the /agents/register endpoint.
    """
    try:
        claims = jwt.decode(
            token,
            settings.secret_key,
            algorithms=["HS256"],
            audience="mcp-gateway-agent",
        )
        return AuthContext(
            authenticated=True,
            auth_type=AuthType.AGENT_TOKEN,
            owner=claims.get("agent_name", "unknown"),
            agent_id=claims.get("agent_id", ""),
            allowed_upstreams=claims.get("allowed_upstreams", []),
            rate_limit_rpm=claims.get("rate_limit_rpm", -1),
            scopes=claims.get("scopes", ["read"]),
            tier=claims.get("tier", "standard"),
            metadata={"agent_claims": claims},
        )
    except jwt.PyJWTError:
        return None


async def _fetch_jwks(oauth: OAuthConfig) -> dict[str, Any]:
    """Fetch and cache JWKS from the OIDC provider."""
    if oauth.jwks_uri in _jwks_cache:
        return _jwks_cache[oauth.jwks_uri]

    async with httpx.AsyncClient() as client:
        resp = await client.get(oauth.jwks_uri, timeout=10.0)
        resp.raise_for_status()
        jwks = resp.json()

    _jwks_cache[oauth.jwks_uri] = jwks
    return jwks


def _get_signing_key(jwks: dict[str, Any], token: str) -> Any:
    """Extract the correct signing key from JWKS for the given token."""
    unverified_header = jwt.get_unverified_header(token)
    kid = unverified_header.get("kid")

    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return jwt.algorithms.RSAAlgorithm.from_jwk(key)

    raise jwt.PyJWTError("No matching key found in JWKS")
