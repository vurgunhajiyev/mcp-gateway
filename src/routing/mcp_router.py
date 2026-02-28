"""
MCP-specific request router (Production-safe version).

- No ORJSON dependency
- FastAPI-native JSON serialization
- Clean error handling
- Safe upstream wrapping
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from src.core.state import AuthContext, GatewayState
from src.protocol.mcp_types import (
    JsonRpcError,
    JsonRpcResponse,
    MCPCapabilities,
    MCPClientInfo,
    MCPGatewayEnvelope,
    MCPGatewayResponse,
    MCPInitializeResult,
    MCPMethod,
    MCPToolDefinition,
)
from src.protocol.validator import MCPValidationError, validate_full_request
from src.routing.proxy import proxy_request

router = APIRouter(prefix="/mcp", tags=["MCP Protocol"])


# =========================================================
# MAIN MCP GATEWAY ENDPOINT
# =========================================================

@router.post("")
@router.post("/")
async def mcp_gateway_endpoint(request: Request) -> Response:
    state: GatewayState = request.app.state.gateway
    start = time.perf_counter()

    try:
        payload = await request.json()
    except Exception:
        return _error_response(None, -32700, "Parse error: invalid JSON")

    try:
        envelope, mcp_method = validate_full_request(payload)
    except MCPValidationError as e:
        return _error_response(
            payload.get("request", {}).get("id"),
            e.code,
            e.message,
            e.data,
        )

    auth: AuthContext = getattr(request.state, "auth", AuthContext())

    if mcp_method == MCPMethod.INITIALIZE:
        return await _handle_initialize(envelope, state, start)

    if mcp_method == MCPMethod.PING:
        return _handle_ping(envelope, state, start)

    if mcp_method == MCPMethod.TOOLS_LIST:
        return await _handle_tools_list(envelope, state, auth, start)

    # Resolve upstream
    upstream_name = envelope.upstream
    upstream = (
        state.resolve_upstream(upstream_name)
        if upstream_name
        else state.get_default_upstream()
    )

    if not upstream:
        return _error_response(
            envelope.request.id,
            -32000,
            f"No upstream found" + (f": {upstream_name}" if upstream_name else ""),
        )

    if not auth.can_access(upstream.name):
        return _error_response(
            envelope.request.id,
            -32000,
            "Access denied to upstream",
        )

    proxy_response = await proxy_request(
        request=request,
        upstream=upstream,
        path="",
        state=state,
    )

    elapsed = (time.perf_counter() - start) * 1000

    # Wrap JSON response from upstream
    content_type = proxy_response.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        try:
            upstream_json = json.loads(proxy_response.body.decode())

            gateway_response = MCPGatewayResponse(
                gateway_id=state.settings.gateway_id,
                session_id=envelope.session_id,
                upstream=upstream.name,
                latency_ms=round(elapsed, 2),
                timestamp=datetime.now(timezone.utc),
                response=JsonRpcResponse(
                    id=envelope.request.id,
                    result=upstream_json.get("result"),
                    error=upstream_json.get("error"),
                ),
            )

            return JSONResponse(
                content=gateway_response.model_dump(mode="json"),
                status_code=proxy_response.status_code,
            )
        except Exception:
            pass

    return proxy_response


# =========================================================
# DIRECT UPSTREAM PROXY (BYPASS ENVELOPE)
# =========================================================

@router.post("/{upstream_name}")
@router.post("/{upstream_name}/{path:path}")
async def mcp_upstream_endpoint(
    request: Request,
    upstream_name: str,
    path: str = "",
) -> Response:
    state: GatewayState = request.app.state.gateway
    auth: AuthContext = getattr(request.state, "auth", AuthContext())

    upstream = state.resolve_upstream(upstream_name)
    if not upstream:
        return JSONResponse(
            {"error": "upstream_not_found", "upstream": upstream_name},
            status_code=404,
        )

    if not auth.can_access(upstream.name):
        return JSONResponse(
            {"error": "access_denied", "upstream": upstream_name},
            status_code=403,
        )

    return await proxy_request(request, upstream, path, state)


# =========================================================
# INTERNAL HANDLERS
# =========================================================

async def _handle_initialize(
    envelope: MCPGatewayEnvelope,
    state: GatewayState,
    start: float,
) -> Response:
    result = MCPInitializeResult(
        protocolVersion="2024-11-05",
        capabilities=MCPCapabilities(
            tools={"listChanged": True},
            resources={"subscribe": True, "listChanged": True},
            prompts={"listChanged": True},
            logging={},
        ),
        serverInfo=MCPClientInfo(
            name="mcp-gateway",
            version="1.0.0",
        ),
    )

    elapsed = (time.perf_counter() - start) * 1000

    response = MCPGatewayResponse(
        gateway_id=state.settings.gateway_id,
        session_id=envelope.session_id,
        latency_ms=round(elapsed, 2),
        response=JsonRpcResponse(
            id=envelope.request.id,
            result=result.model_dump(),
        ),
    )

    return JSONResponse(content=response.model_dump(mode="json"))


def _handle_ping(
    envelope: MCPGatewayEnvelope,
    state: GatewayState,
    start: float,
) -> Response:
    elapsed = (time.perf_counter() - start) * 1000

    response = MCPGatewayResponse(
        gateway_id=state.settings.gateway_id,
        latency_ms=round(elapsed, 2),
        response=JsonRpcResponse(id=envelope.request.id, result={}),
    )

    return JSONResponse(content=response.model_dump(mode="json"))


async def _handle_tools_list(
    envelope: MCPGatewayEnvelope,
    state: GatewayState,
    auth: AuthContext,
    start: float,
) -> Response:
    tools: list[dict[str, Any]] = []

    for upstream in state.settings.upstreams:
        if not auth.can_access(upstream.name):
            continue

        tools.append(
            MCPToolDefinition(
                name=f"{upstream.name}.proxy",
                description=f"Proxy to {upstream.name}: {upstream.description}",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "method": {"type": "string"},
                        "params": {"type": "object"},
                    },
                    "required": ["method"],
                },
            ).model_dump()
        )

    elapsed = (time.perf_counter() - start) * 1000

    response = MCPGatewayResponse(
        gateway_id=state.settings.gateway_id,
        session_id=envelope.session_id,
        latency_ms=round(elapsed, 2),
        response=JsonRpcResponse(
            id=envelope.request.id,
            result={"tools": tools},
        ),
    )

    return JSONResponse(content=response.model_dump(mode="json"))


def _error_response(
    request_id: Any,
    code: int,
    message: str,
    data: Any = None,
) -> Response:
    response = JsonRpcResponse(
        id=request_id or 0,
        error=JsonRpcError(code=code, message=message, data=data),
    )

    return JSONResponse(
        content=response.model_dump(mode="json"),
        status_code=400 if code != -32603 else 500,
    )