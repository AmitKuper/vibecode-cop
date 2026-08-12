"""Security and end-to-end discovery contracts for adaptive MCP: transports."""

from __future__ import annotations

import sys

import pytest

from cop_worker.mcp.client import GameMCPClient
from cop_worker.protocol.introspector import IntrospectionResult, MCPIntrospector
from cop_worker.protocol.pipeline import verify_locked_schema
from cop_worker.protocol.profile import ProtocolProfile
from cop_worker.protocol.transport_probe import ProbeResult, TransportType, normalize_mcp_base_url


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://team.com/mcp", "https://team.com"),
        ("https://team.com/sse/", "https://team.com"),
        ("https://team.example/custom/mcp", "https://team.example/custom"),
        ("https://team.example/custom", "https://team.example/custom"),
    ],
)
def test_endpoint_normalization_removes_only_exact_transport_suffix(value, expected) -> None:
    assert normalize_mcp_base_url(value) == expected


def test_game_client_uses_discovered_transport() -> None:
    client = GameMCPClient("https://team.com/mcp", "test-secret")
    assert client._transport.url == "https://team.com/sse"
    client.configure_transport("streamable_http", "https://team.com/mcp")
    assert client._transport.url == "https://team.com/mcp"
    client.configure_transport("sse", "https://team.com/sse")
    assert client._transport.url == "https://team.com/sse"
    with pytest.raises(ValueError, match="Unsupported"):
        client.configure_transport("stdio", "stdio")


@pytest.mark.asyncio
async def test_locked_schema_recheck_rejects_mid_series_change(monkeypatch) -> None:
    profile = ProtocolProfile.native()

    async def changed(_self, _probe):
        return IntrospectionResult("peer", "1", "p", [], [], [], {}, "changed")

    monkeypatch.setattr("cop_worker.protocol.pipeline.MCPIntrospector.introspect", changed)
    with pytest.raises(Exception, match="schema changed"):
        await verify_locked_schema(profile)


@pytest.mark.asyncio
async def test_stdio_transport_introspects_a_real_fixture_process(tmp_path) -> None:
    script = tmp_path / "stdio_peer.py"
    script.write_text(
        "from fastmcp import FastMCP\n"
        "mcp = FastMCP('stdio-peer')\n"
        "@mcp.tool\n"
        "def action(game_id: str, role: str, phase: str) -> dict:\n"
        "    return {'ok': False, 'error': 'probe'}\n"
        "if __name__ == '__main__':\n"
        "    mcp.run()\n",
        encoding="utf-8",
    )
    probe = ProbeResult(
        TransportType.STDIO,
        "stdio",
        "stdio",
        0.0,
        "fixture",
        (sys.executable, str(script)),
    )
    result = await MCPIntrospector(timeout_s=15).introspect(probe)
    assert result.tool_names() == ["action"]
