"""
MCP Protocol type definitions.

Implements the Model Context Protocol (MCP) message format for:
- JSON-RPC 2.0 based request/response
- Tool invocation
- Resource access
- Prompt handling
- Agent session management
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# JSON-RPC 2.0 Base Types
# ──────────────────────────────────────────────

class JsonRpcRequest(BaseModel):
    """JSON-RPC 2.0 request message."""

    jsonrpc: Literal["2.0"] = "2.0"
    id: Union[str, int]
    method: str
    params: Optional[dict[str, Any]] = None


class JsonRpcResponse(BaseModel):
    """JSON-RPC 2.0 response message."""

    jsonrpc: Literal["2.0"] = "2.0"
    id: Union[str, int]
    result: Optional[Any] = None
    error: Optional["JsonRpcError"] = None


class JsonRpcError(BaseModel):
    """JSON-RPC 2.0 error object."""

    code: int
    message: str
    data: Optional[Any] = None


# ──────────────────────────────────────────────
# MCP-Specific Method Enumeration
# ──────────────────────────────────────────────

class MCPMethod(str, Enum):
    # Lifecycle
    INITIALIZE = "initialize"
    INITIALIZED = "notifications/initialized"
    SHUTDOWN = "shutdown"
    PING = "ping"

    # Tools
    TOOLS_LIST = "tools/list"
    TOOLS_CALL = "tools/call"

    # Resources
    RESOURCES_LIST = "resources/list"
    RESOURCES_READ = "resources/read"
    RESOURCES_SUBSCRIBE = "resources/subscribe"

    # Prompts
    PROMPTS_LIST = "prompts/list"
    PROMPTS_GET = "prompts/get"

    # Logging
    LOG_SET_LEVEL = "logging/setLevel"

    # Completion
    COMPLETION_COMPLETE = "completion/complete"


# ──────────────────────────────────────────────
# MCP Initialize
# ──────────────────────────────────────────────

class MCPClientInfo(BaseModel):
    """Client capabilities sent during initialization."""

    name: str
    version: str


class MCPCapabilities(BaseModel):
    """Server capabilities returned during initialization."""

    tools: Optional[dict[str, Any]] = None
    resources: Optional[dict[str, Any]] = None
    prompts: Optional[dict[str, Any]] = None
    logging: Optional[dict[str, Any]] = None


class MCPInitializeParams(BaseModel):
    """Parameters for the initialize request."""

    protocolVersion: str = "2024-11-05"
    capabilities: dict[str, Any] = Field(default_factory=dict)
    clientInfo: MCPClientInfo


class MCPInitializeResult(BaseModel):
    """Result of the initialize request."""

    protocolVersion: str = "2024-11-05"
    capabilities: MCPCapabilities
    serverInfo: MCPClientInfo


# ──────────────────────────────────────────────
# MCP Tools
# ──────────────────────────────────────────────

class MCPToolDefinition(BaseModel):
    """Definition of a tool exposed via MCP."""

    name: str
    description: str = ""
    inputSchema: dict[str, Any] = Field(default_factory=dict)


class MCPToolCallParams(BaseModel):
    """Parameters for tools/call."""

    name: str
    arguments: Optional[dict[str, Any]] = None


class MCPToolResult(BaseModel):
    """Result of a tool call."""

    content: list["MCPContent"]
    isError: bool = False


class MCPContent(BaseModel):
    """Content block in MCP responses."""

    type: str = "text"  # text | image | resource
    text: Optional[str] = None
    mimeType: Optional[str] = None
    data: Optional[str] = None  # base64 for images
    uri: Optional[str] = None


# ──────────────────────────────────────────────
# MCP Resources
# ──────────────────────────────────────────────

class MCPResource(BaseModel):
    """A resource available via MCP."""

    uri: str
    name: str
    description: str = ""
    mimeType: str = "text/plain"


class MCPResourceReadParams(BaseModel):
    """Parameters for resources/read."""

    uri: str


# ──────────────────────────────────────────────
# MCP Prompts
# ──────────────────────────────────────────────

class MCPPromptDefinition(BaseModel):
    """A prompt template available via MCP."""

    name: str
    description: str = ""
    arguments: list[dict[str, Any]] = Field(default_factory=list)


class MCPPromptMessage(BaseModel):
    """A message in a prompt response."""

    role: str  # user | assistant
    content: MCPContent


# ──────────────────────────────────────────────
# Gateway Extensions — Agent Session & Routing
# ──────────────────────────────────────────────

class MCPGatewayEnvelope(BaseModel):
    """
    Gateway-level wrapper around MCP messages.
    This is the top-level format the gateway receives from agents.
    """

    version: str = "1.0"
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    upstream: Optional[str] = None  # target upstream name
    api_version: str = "v1"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    request: JsonRpcRequest
    metadata: dict[str, Any] = Field(default_factory=dict)


class MCPGatewayResponse(BaseModel):
    """
    Gateway-level response wrapper.
    """

    version: str = "1.0"
    gateway_id: str = ""
    session_id: Optional[str] = None
    upstream: Optional[str] = None
    latency_ms: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    response: JsonRpcResponse
    metadata: dict[str, Any] = Field(default_factory=dict)
