"""
Proxy router — routes MCP requests to downstream API upstreams.
"""

from __future__ import annotations

import math
import httpx
from fastapi import Request, Response
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.core.config import UpstreamServer
from src.core.state import AuthContext, GatewayState
from src.middleware.circuit_breaker import (
    CircuitBreakerError,
    check_circuit,
    record_failure,
    record_success,
)

# Hop-by-hop headers (must not be forwarded)
HOP_BY_HOP_HEADERS = frozenset({
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "host",
})


async def proxy_request(
    request: Request,
    upstream: UpstreamServer,
    path: str,
    state: GatewayState,
) -> Response:

    # Circuit breaker check
    cb = state.get_circuit_breaker(upstream.name)

    try:
        await check_circuit(cb, upstream.name, state.settings)
    except CircuitBreakerError as e:
        return Response(
            content=f'{{"error":"circuit_open","upstream":"{e.upstream_name}","retry_after":{e.retry_after:.1f}}}',
            status_code=503,
            media_type="application/json",
            headers={"Retry-After": str(math.ceil(e.retry_after))},
        )

    # Build URL
    upstream_url = f"{upstream.url.rstrip('/')}/{path.lstrip('/')}"
    if request.url.query:
        upstream_url += f"?{request.url.query}"

    headers = _build_upstream_headers(request, upstream)
    body = await request.body()

    try:
        response = await _send_with_retry(
            client=state.http_client,
            method=request.method,
            url=upstream_url,
            headers=headers,
            body=body,
            upstream=upstream,
        )

        await record_success(cb)

        # 🔥 FIX: fully read response to avoid chunked transfer issues
        content = await response.aread()

        # Filter headers
        resp_headers = {
            k: v
            for k, v in response.headers.items()
            if k.lower() not in HOP_BY_HOP_HEADERS
        }

        # Reset content-length properly
        resp_headers.pop("content-length", None)
        resp_headers["Content-Length"] = str(len(content))

        resp_headers["X-Upstream"] = upstream.name
        resp_headers["X-Upstream-Version"] = upstream.version

        return Response(
            content=content,
            status_code=response.status_code,
            headers=resp_headers,
            media_type=response.headers.get("content-type", "application/json"),
        )

    except httpx.ConnectTimeout:
        await record_failure(cb, state.settings)
        return Response(
            content=f'{{"error":"connect_timeout","upstream":"{upstream.name}"}}',
            status_code=504,
            media_type="application/json",
        )

    except httpx.ReadTimeout:
        await record_failure(cb, state.settings)
        return Response(
            content=f'{{"error":"read_timeout","upstream":"{upstream.name}"}}',
            status_code=504,
            media_type="application/json",
        )

    except (httpx.ConnectError, httpx.RemoteProtocolError) as exc:
        await record_failure(cb, state.settings)
        return Response(
            content=f'{{"error":"upstream_unreachable","upstream":"{upstream.name}","detail":"{type(exc).__name__}"}}',
            status_code=502,
            media_type="application/json",
        )

    except RetryError:
        await record_failure(cb, state.settings)
        return Response(
            content=f'{{"error":"upstream_retry_exhausted","upstream":"{upstream.name}"}}',
            status_code=502,
            media_type="application/json",
        )


async def _send_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes,
    upstream: UpstreamServer,
) -> httpx.Response:

    @retry(
        stop=stop_after_attempt(upstream.max_retries),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=5.0),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.RemoteProtocolError)),
        reraise=True,
    )
    async def _do_send() -> httpx.Response:
        resp = await client.request(
            method=method,
            url=url,
            headers=headers,
            content=body,
            timeout=httpx.Timeout(
                connect=upstream.connect_timeout,
                read=upstream.timeout_seconds,
                write=10.0,
                pool=5.0,
            ),
        )

        if resp.status_code in (502, 503, 504):
            raise httpx.RemoteProtocolError(
                f"Upstream returned {resp.status_code}",
                request=resp.request,
            )

        return resp

    return await _do_send()


def _build_upstream_headers(request: Request, upstream: UpstreamServer) -> dict[str, str]:
    headers: dict[str, str] = {}

    for key, value in request.headers.items():
        if key.lower() not in HOP_BY_HOP_HEADERS:
            headers[key] = value

    if upstream.upstream_token:
        headers["Authorization"] = f"Bearer {upstream.upstream_token}"

    auth: AuthContext = getattr(request.state, "auth", AuthContext())
    headers["X-Forwarded-For"] = _get_client_ip(request)
    headers["X-Gateway-Request-Id"] = request.headers.get("x-request-id", "")
    headers["X-Gateway-Auth-Owner"] = auth.owner if auth.authenticated else ""

    return headers


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return ""