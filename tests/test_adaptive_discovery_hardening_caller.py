"""Security and end-to-end discovery contracts for adaptive MCP: tool callers."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from cop_worker.mcp.client import GameMCPClient
from cop_worker.protocol.pipeline import (
    _discovered_tool_caller,
    run_adaptive_negotiation,
)
from cop_worker.protocol.transport_probe import ProbeResult, TransportType


@pytest.mark.asyncio
async def test_full_stdio_discovery_conformance_and_profile_lock(tmp_path) -> None:
    script = tmp_path / "stdio_signed_peer.py"
    script.write_text(
        "from fastmcp import FastMCP\n"
        "import json\n"
        "mcp = FastMCP('stdio-signed-peer')\n"
        "@mcp.tool\n"
        "def start_game(message_json: str, signature: str) -> dict:\n"
        "    body = json.loads(message_json)\n"
        "    return {'ok': False, 'error': 'invalid probe signature',\n"
        "            'game_id': body['game_id'], 'phase': 'start_game'}\n"
        "@mcp.tool\n"
        "def action(game_id: str, message_json: str, signature: str) -> dict:\n"
        "    body = json.loads(message_json)\n"
        "    return {'ok': False, 'error': 'invalid probe signature',\n"
        "            'game_id': game_id, 'phase': body['phase']}\n"
        "@mcp.tool\n"
        "def protocol_conformance(phase: str, game_id: str, request_digest: str,\n"
        "                         idempotency_key: str) -> dict:\n"
        "    return {'ok': True, 'game_id': game_id, 'phase': phase,\n"
        "            'idempotent': True, 'side_effects': 0,\n"
        "            'canonical_order': True, 'canonical_json_bytes': True,\n"
        "            'commitment_binding': True, 'nonce_final_audit_only': True,\n"
        "            'comprehensive_audit': True, 'result_agreement': True}\n"
        "if __name__ == '__main__':\n"
        "    mcp.run()\n",
        encoding="utf-8",
    )
    result = await run_adaptive_negotiation(
        f'stdio://"{sys.executable}" "{script}"',
        cache_dir=tmp_path / "profiles",
        introspect_timeout_s=15,
    )
    assert result.is_compatible
    assert result.profile.remote_transport == "stdio"
    assert result.profile.remote_stdio_command == (sys.executable, str(script))
    assert result.profile.verify_integrity()
    client = GameMCPClient("http://unused.example/mcp", "secret")
    client.configure_transport("stdio", "stdio", result.profile.remote_stdio_command)
    assert type(client._transport).__name__ == "StdioTransport"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "is_error", "expected"),
    [
        ([], False, {"ok": True}),
        ([SimpleNamespace(text="bad")], True, {"ok": False, "error": "bad"}),
        ([SimpleNamespace(text="not-json")], False, {"ok": True, "raw": "not-json"}),
        ([SimpleNamespace(text="[1,2]")], False, {"ok": True, "raw": [1, 2]}),
        ([SimpleNamespace(text='{"ok":false}')], False, {"ok": False}),
    ],
)
async def test_discovered_caller_normalizes_result_shapes(monkeypatch, content, is_error, expected):
    class FakeClient:
        def __init__(self, _transport):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def call_tool(self, _tool, _params):
            return SimpleNamespace(content=content, is_error=is_error)

    monkeypatch.setattr("fastmcp.Client", FakeClient)
    probe = ProbeResult(TransportType.SSE, "http://peer", "http://peer/sse", 0.0, "test")
    assert await _discovered_tool_caller(probe)("action", {}) == expected


def test_discovered_caller_supports_streamable_stdio_and_rejects_unknown() -> None:
    streamable = ProbeResult(
        TransportType.STREAMABLE_HTTP, "http://peer", "http://peer/mcp", 0.0, "test"
    )
    stdio = ProbeResult(
        TransportType.STDIO, "stdio", "stdio", 0.0, "test", (sys.executable, "peer.py")
    )
    assert callable(_discovered_tool_caller(streamable))
    assert callable(_discovered_tool_caller(stdio))
    with pytest.raises(Exception, match="No remote caller"):
        _discovered_tool_caller(
            ProbeResult(TransportType.UNKNOWN, "unknown", "unknown", 0.0, "test")
        )
