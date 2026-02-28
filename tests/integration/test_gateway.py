"""Integration tests for the full gateway stack."""
import pytest
from fastapi.testclient import TestClient

from src.core.app import create_app
from src.core.config import ApiKeyEntry, GatewaySettings, UpstreamServer


@pytest.fixture
def settings():
    return GatewaySettings(
        secret_key="test-secret-key",
        auth_enabled=True,
        api_keys=[
            ApiKeyEntry(
                key="test-key-001",
                owner="test-user",
                scopes=["read", "write"],
            ),
        ],
        upstreams=[
            UpstreamServer(
                name="mock-upstream",
                url="http://localhost:9999",
                description="Mock upstream for testing",
            ),
        ],
    )


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    return TestClient(app)


class TestHealthEndpoints:
    def test_liveness(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_readiness(self, client):
        resp = client.get("/readyz")
        assert resp.status_code in (200, 207)


class TestAuthentication:
    def test_unauthenticated_request(self, client):
        resp = client.post("/mcp", json={"test": True})
        assert resp.status_code == 401

    def test_valid_api_key(self, client):
        resp = client.get(
            "/upstreams",
            headers={"X-Api-Key": "test-key-001"},
        )
        assert resp.status_code == 200

    def test_invalid_api_key(self, client):
        resp = client.get(
            "/upstreams",
            headers={"X-Api-Key": "wrong-key"},
        )
        assert resp.status_code == 401


class TestMCPProtocol:
    def test_mcp_initialize(self, client):
        resp = client.post(
            "/mcp",
            json={
                "version": "1.0",
                "request": {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "clientInfo": {"name": "test", "version": "1.0"},
                    },
                },
            },
            headers={"X-Api-Key": "test-key-001"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["response"]["result"]["protocolVersion"] == "2024-11-05"

    def test_mcp_ping(self, client):
        resp = client.post(
            "/mcp",
            json={
                "request": {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "ping",
                },
            },
            headers={"X-Api-Key": "test-key-001"},
        )
        assert resp.status_code == 200

    def test_mcp_invalid_method(self, client):
        resp = client.post(
            "/mcp",
            json={
                "request": {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "invalid/method",
                },
            },
            headers={"X-Api-Key": "test-key-001"},
        )
        assert resp.status_code == 400

    def test_mcp_tools_list(self, client):
        resp = client.post(
            "/mcp",
            json={
                "request": {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/list",
                },
            },
            headers={"X-Api-Key": "test-key-001"},
        )
        assert resp.status_code == 200
        data = resp.json()
        tools = data["response"]["result"]["tools"]
        assert len(tools) == 1
        assert tools[0]["name"] == "mock-upstream.proxy"


class TestAgentRegistration:
    def test_register_agent(self, client):
        resp = client.post(
            "/agents/register",
            json={
                "agent_name": "test-agent",
                "agent_version": "1.0.0",
                "requested_upstreams": ["mock-upstream"],
                "requested_scopes": ["read"],
            },
            headers={"X-Api-Key": "test-key-001"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "token" in data
        assert data["agent_id"].startswith("agent_")

    def test_agent_token_auth(self, client):
        # Register
        reg = client.post(
            "/agents/register",
            json={"agent_name": "auth-test-agent"},
            headers={"X-Api-Key": "test-key-001"},
        )
        token = reg.json()["token"]

        # Use agent token
        resp = client.get(
            "/upstreams",
            headers={"X-Agent-Token": token},
        )
        assert resp.status_code == 200


class TestConfigEndpoints:
    def test_list_upstreams(self, client):
        resp = client.get(
            "/upstreams",
            headers={"X-Api-Key": "test-key-001"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "mock-upstream"

    def test_config_info(self, client):
        resp = client.get(
            "/config/info",
            headers={"X-Api-Key": "test-key-001"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["auth_enabled"] is True
        assert data["upstream_count"] == 1
