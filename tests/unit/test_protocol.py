"""Tests for MCP protocol validation."""
import pytest

from src.protocol.mcp_types import MCPMethod
from src.protocol.validator import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    MCPValidationError,
    validate_full_request,
    validate_gateway_envelope,
    validate_jsonrpc_request,
    validate_mcp_method,
)


class TestJsonRpcValidation:
    def test_valid_request(self):
        req = validate_jsonrpc_request({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
        })
        assert req.method == "tools/list"
        assert req.id == 1

    def test_missing_jsonrpc_version(self):
        with pytest.raises(MCPValidationError) as exc:
            validate_jsonrpc_request({"id": 1, "method": "test"})
        assert exc.value.code == INVALID_REQUEST

    def test_missing_method(self):
        with pytest.raises(MCPValidationError):
            validate_jsonrpc_request({"jsonrpc": "2.0", "id": 1})

    def test_missing_id(self):
        with pytest.raises(MCPValidationError):
            validate_jsonrpc_request({"jsonrpc": "2.0", "method": "test"})


class TestMCPMethodValidation:
    def test_valid_methods(self):
        assert validate_mcp_method("initialize") == MCPMethod.INITIALIZE
        assert validate_mcp_method("tools/list") == MCPMethod.TOOLS_LIST
        assert validate_mcp_method("tools/call") == MCPMethod.TOOLS_CALL

    def test_unknown_method(self):
        with pytest.raises(MCPValidationError) as exc:
            validate_mcp_method("unknown/method")
        assert exc.value.code == METHOD_NOT_FOUND


class TestGatewayEnvelopeValidation:
    def test_valid_envelope(self):
        envelope = validate_gateway_envelope({
            "version": "1.0",
            "upstream": "notion",
            "request": {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
            },
        })
        assert envelope.upstream == "notion"
        assert envelope.request.method == "tools/list"

    def test_minimal_envelope(self):
        envelope = validate_gateway_envelope({
            "request": {
                "jsonrpc": "2.0",
                "id": "abc",
                "method": "ping",
            },
        })
        assert envelope.request.id == "abc"


class TestFullValidation:
    def test_valid_initialize(self):
        envelope, method = validate_full_request({
            "upstream": "notion",
            "request": {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "clientInfo": {"name": "test-agent", "version": "1.0"},
                },
            },
        })
        assert method == MCPMethod.INITIALIZE

    def test_valid_tools_call(self):
        envelope, method = validate_full_request({
            "request": {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "my_tool", "arguments": {"x": 1}},
            },
        })
        assert method == MCPMethod.TOOLS_CALL

    def test_tools_call_missing_params(self):
        with pytest.raises(MCPValidationError) as exc:
            validate_full_request({
                "request": {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                },
            })
        assert exc.value.code == INVALID_PARAMS
