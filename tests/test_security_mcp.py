import pytest
from fastapi.testclient import TestClient
from fastmcp import Client
from fastmcp.server.auth import AccessToken
from fastmcp.server.auth.providers.github import GitHubProvider

from app.core.config import settings
from app.main import create_app
from app.mcp_server import mcp
from app.services.mcp_auth import OwnerGitHubProvider, StaticVerifier

TOKEN = "a-secure-static-token-0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def test_disabled_mcp_denies_anonymous(anonymous_client):
    for method in ("get", "post", "delete"):
        response = getattr(anonymous_client, method)("/mcp")
        assert response.status_code == 401


def test_remote_mcp_requires_bearer(monkeypatch):
    monkeypatch.setattr(settings, "MCP_TOKEN", TOKEN)
    with TestClient(create_app(), base_url=settings.BASE_URL) as client:
        for path in ("/mcp", "/mcp/"):
            assert client.post(path, json={}).status_code == 401
        assert client.post("/mcp", headers={"Authorization": "Bearer wrong"}, json={}).status_code == 401
        response = client.post("/mcp", headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/json, text/event-stream"},
                               json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}})
        assert response.status_code == 200, response.text


@pytest.mark.anyio
async def test_mcp_tool_listing():
    async with Client(mcp) as client:
        tools = {tool.name for tool in await client.list_tools()}
        assert {"get_overview", "get_debts", "list_transactions", "add_transaction", "log_weight", "add_to_home_list"} <= tools


@pytest.mark.anyio
async def test_static_token_verification(monkeypatch):
    monkeypatch.setattr(settings, "MCP_TOKEN", TOKEN)
    verifier = StaticVerifier()
    assert await verifier.verify_token(TOKEN)
    assert await verifier.verify_token(TOKEN + "wrong") is None


@pytest.mark.anyio
async def test_github_allowlist_at_http_verifier(monkeypatch):
    monkeypatch.setattr(settings, "GITHUB_ALLOWED_LOGIN", "Owner")
    monkeypatch.setattr(settings, "MCP_TOKEN", "")

    async def upstream(self, token):
        return AccessToken(token=token, client_id="test", scopes=[], claims={"login": token})

    monkeypatch.setattr(GitHubProvider, "verify_token", upstream)
    provider = object.__new__(OwnerGitHubProvider)
    assert await provider.verify_token("owner")
    assert await provider.verify_token("attacker") is None


def test_partial_oauth_does_not_enable_remote(monkeypatch):
    monkeypatch.setattr(settings, "GITHUB_CLIENT_ID", "id-only")
    monkeypatch.setattr(settings, "GITHUB_CLIENT_SECRET", "")
    monkeypatch.setattr(settings, "MCP_TOKEN", "")
    assert not settings.remote_mcp_enabled
