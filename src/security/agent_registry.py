"""
AI Agent registration and session management.

Agents register with the gateway to receive a session token,
which they use for subsequent MCP requests. This provides:
- Agent identity tracking
- Per-agent rate limits and permissions
- Session lifecycle management
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from pydantic import BaseModel, Field

from src.core.config import GatewaySettings


class AgentRegistration(BaseModel):
    """Agent registration request."""

    agent_name: str
    agent_version: str = "1.0.0"
    capabilities: list[str] = Field(default_factory=list)
    requested_upstreams: list[str] = Field(default_factory=list)
    requested_scopes: list[str] = Field(default_factory=lambda: ["read"])
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentSession(BaseModel):
    """Active agent session."""

    agent_id: str
    agent_name: str
    agent_version: str
    token: str
    allowed_upstreams: list[str]
    scopes: list[str]
    tier: str
    created_at: datetime
    expires_at: datetime
    last_activity: datetime
    request_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRegistryError(Exception):
    """Agent registration or session error."""

    pass


class AgentRegistry:
    """
    Manages agent registration, token issuance, and session lifecycle.
    In production, back this with Redis or a database.
    """

    def __init__(self, settings: GatewaySettings) -> None:
        self.settings = settings
        self._sessions: dict[str, AgentSession] = {}
        self._token_ttl = timedelta(hours=24)

    async def register_agent(self, registration: AgentRegistration) -> AgentSession:
        """
        Register a new agent and issue a session token.

        Validates requested upstreams and scopes against gateway policy,
        then creates a signed JWT for the agent to use.
        """
        agent_id = f"agent_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        expires = now + self._token_ttl

        # Resolve allowed upstreams (intersection of requested + configured)
        configured_names = {u.name for u in self.settings.upstreams}
        if registration.requested_upstreams:
            allowed = [
                u for u in registration.requested_upstreams if u in configured_names
            ]
        else:
            allowed = list(configured_names)

        # Resolve scopes
        valid_scopes = {"read", "write", "admin"}
        scopes = [s for s in registration.requested_scopes if s in valid_scopes]
        if not scopes:
            scopes = ["read"]

        # Issue JWT token
        token_payload = {
            "agent_id": agent_id,
            "agent_name": registration.agent_name,
            "agent_version": registration.agent_version,
            "allowed_upstreams": allowed,
            "scopes": scopes,
            "tier": "standard",
            "rate_limit_rpm": self.settings.rate_limit.default_rpm,
            "aud": "mcp-gateway-agent",
            "iat": int(now.timestamp()),
            "exp": int(expires.timestamp()),
        }

        token = jwt.encode(token_payload, self.settings.secret_key, algorithm="HS256")

        session = AgentSession(
            agent_id=agent_id,
            agent_name=registration.agent_name,
            agent_version=registration.agent_version,
            token=token,
            allowed_upstreams=allowed,
            scopes=scopes,
            tier="standard",
            created_at=now,
            expires_at=expires,
            last_activity=now,
            metadata=registration.metadata,
        )

        self._sessions[agent_id] = session
        return session

    async def get_session(self, agent_id: str) -> Optional[AgentSession]:
        """Get an active agent session."""
        session = self._sessions.get(agent_id)
        if session and session.expires_at > datetime.now(timezone.utc):
            return session
        return None

    async def refresh_activity(self, agent_id: str) -> None:
        """Update last activity timestamp and increment request count."""
        session = self._sessions.get(agent_id)
        if session:
            session.last_activity = datetime.now(timezone.utc)
            session.request_count += 1

    async def revoke_session(self, agent_id: str) -> bool:
        """Revoke an agent session."""
        return self._sessions.pop(agent_id, None) is not None

    async def list_active_sessions(self) -> list[AgentSession]:
        """List all non-expired sessions."""
        now = datetime.now(timezone.utc)
        active = [s for s in self._sessions.values() if s.expires_at > now]
        return active

    async def cleanup_expired(self) -> int:
        """Remove expired sessions. Call periodically."""
        now = datetime.now(timezone.utc)
        expired = [k for k, v in self._sessions.items() if v.expires_at <= now]
        for k in expired:
            del self._sessions[k]
        return len(expired)
