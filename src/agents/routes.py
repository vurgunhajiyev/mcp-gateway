"""
Agent management API routes.

Provides endpoints for AI agents to:
- Register and receive a session token
- List their active sessions
- Revoke sessions
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import ORJSONResponse

from src.security.agent_registry import AgentRegistration, AgentRegistry

router = APIRouter(prefix="/agents", tags=["Agent Management"])


@router.post("/register")
async def register_agent(request: Request, registration: AgentRegistration) -> ORJSONResponse:
    """
    Register a new AI agent and receive a session token.

    The agent provides its name, version, and requested capabilities.
    The gateway validates the request and issues a JWT token scoped
    to the agent's permissions.
    """
    registry: AgentRegistry = request.app.state.agent_registry

    try:
        session = await registry.register_agent(registration)
    except Exception as e:
        return ORJSONResponse(
            {"error": "registration_failed", "detail": str(e)},
            status_code=400,
        )

    return ORJSONResponse(
        {
            "agent_id": session.agent_id,
            "token": session.token,
            "allowed_upstreams": session.allowed_upstreams,
            "scopes": session.scopes,
            "tier": session.tier,
            "expires_at": session.expires_at.isoformat(),
        },
        status_code=201,
    )


@router.get("/sessions")
async def list_sessions(request: Request) -> ORJSONResponse:
    """List all active agent sessions (admin only)."""
    registry: AgentRegistry = request.app.state.agent_registry
    sessions = await registry.list_active_sessions()

    return ORJSONResponse([
        {
            "agent_id": s.agent_id,
            "agent_name": s.agent_name,
            "agent_version": s.agent_version,
            "tier": s.tier,
            "created_at": s.created_at.isoformat(),
            "expires_at": s.expires_at.isoformat(),
            "last_activity": s.last_activity.isoformat(),
            "request_count": s.request_count,
        }
        for s in sessions
    ])


@router.delete("/sessions/{agent_id}")
async def revoke_session(request: Request, agent_id: str) -> ORJSONResponse:
    """Revoke a specific agent session."""
    registry: AgentRegistry = request.app.state.agent_registry
    revoked = await registry.revoke_session(agent_id)

    if not revoked:
        return ORJSONResponse(
            {"error": "session_not_found", "agent_id": agent_id},
            status_code=404,
        )

    return ORJSONResponse({"status": "revoked", "agent_id": agent_id})
