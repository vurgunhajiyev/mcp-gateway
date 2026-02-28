"""
MCP Protocol validator.

Validates incoming MCP requests against the protocol specification,
checks for required fields, validates method names, and ensures
parameter schemas are correct.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import ValidationError

from src.protocol.mcp_types import (
    JsonRpcRequest,
    MCPGatewayEnvelope,
    MCPInitializeParams,
    MCPMethod,
    MCPResourceReadParams,
    MCPToolCallParams,
)


class MCPValidationError(Exception):
    """Raised when an MCP message fails validation."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)


# JSON-RPC 2.0 error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def validate_jsonrpc_request(payload: dict[str, Any]) -> JsonRpcRequest:
    """Validate a raw dict as a JSON-RPC 2.0 request."""
    if not isinstance(payload, dict):
        raise MCPValidationError(PARSE_ERROR, "Request must be a JSON object")

    if payload.get("jsonrpc") != "2.0":
        raise MCPValidationError(INVALID_REQUEST, "jsonrpc field must be '2.0'")

    if "method" not in payload:
        raise MCPValidationError(INVALID_REQUEST, "Missing required field: method")

    if "id" not in payload:
        raise MCPValidationError(INVALID_REQUEST, "Missing required field: id")

    try:
        return JsonRpcRequest.model_validate(payload)
    except ValidationError as e:
        raise MCPValidationError(INVALID_REQUEST, f"Invalid request structure: {e}") from e


def validate_gateway_envelope(payload: dict[str, Any]) -> MCPGatewayEnvelope:
    """Validate the full gateway envelope format."""
    try:
        return MCPGatewayEnvelope.model_validate(payload)
    except ValidationError as e:
        raise MCPValidationError(
            INVALID_REQUEST,
            f"Invalid gateway envelope: {e}",
        ) from e


def validate_mcp_method(method: str) -> MCPMethod:
    """Validate that the method is a known MCP method."""
    try:
        return MCPMethod(method)
    except ValueError:
        raise MCPValidationError(
            METHOD_NOT_FOUND,
            f"Unknown MCP method: {method}",
            data={"known_methods": [m.value for m in MCPMethod]},
        )


def validate_method_params(method: MCPMethod, params: Optional[dict[str, Any]]) -> Any:
    """Validate parameters for a specific MCP method."""
    validators = {
        MCPMethod.INITIALIZE: MCPInitializeParams,
        MCPMethod.TOOLS_CALL: MCPToolCallParams,
        MCPMethod.RESOURCES_READ: MCPResourceReadParams,
    }

    validator_model = validators.get(method)
    if validator_model is None:
        return params  # no specific validation for this method

    if params is None:
        raise MCPValidationError(INVALID_PARAMS, f"Method {method.value} requires parameters")

    try:
        return validator_model.model_validate(params)
    except ValidationError as e:
        raise MCPValidationError(
            INVALID_PARAMS,
            f"Invalid parameters for {method.value}: {e}",
        ) from e


def validate_full_request(payload: dict[str, Any]) -> tuple[MCPGatewayEnvelope, MCPMethod]:
    """
    Full validation pipeline:
    1. Validate envelope structure
    2. Validate inner JSON-RPC request
    3. Validate MCP method
    4. Validate method-specific params
    """
    envelope = validate_gateway_envelope(payload)
    mcp_method = validate_mcp_method(envelope.request.method)
    validate_method_params(mcp_method, envelope.request.params)
    return envelope, mcp_method
