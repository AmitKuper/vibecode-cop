"""Behavioral tests for cop_worker.mcp.client.GameMCPClient with a fake fastmcp Client."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastmcp.client.transports import SSETransport, StdioTransport, StreamableHttpTransport

import cop_worker.mcp.client as client_mod
from cop_worker.mcp.client import GameMCPClient
from cop_worker.mcp.messages import ActionMessage, StartGameMessage

_SHA = "a" * 64


class _Text:
    def __init__(self, text: str) -> None:
        self.text = text


class _Result:
    def __init__(self, content, is_error=False) -> None:
        self.content = content
        self.is_error = is_error


class _FakeClient:
    """Async context manager standing in for fastmcp.Client."""

    calls: list = []
    result: _Result = _Result([_Text("{}")])
    raise_exc: Exception | None = None

    def __init__(self, transport) -> None:
        self.transport = transport

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def call_tool(self, tool_name, params):
        _FakeClient.calls.append((tool_name, params))
        if _FakeClient.raise_exc is not None:
            raise _FakeClient.raise_exc
        return _FakeClient.result


@pytest.fixture()
def fake_client(monkeypatch):
    monkeypatch.setattr(client_mod, "Client", _FakeClient)
    _FakeClient.calls = []
    _FakeClient.raise_exc = None
    _FakeClient.result = _Result([_Text(json.dumps({"ok": True, "phase": "commit"}))])
    return _FakeClient


def _client() -> GameMCPClient:
    return GameMCPClient("http://localhost:5001/mcp", secret="s3cret", timeout_seconds=2.0)


def test_configure_transport_variants():
    c = _client()
    assert isinstance(c._transport, SSETransport)
    c.configure_transport("sse", "http://h/sse")
    assert isinstance(c._transport, SSETransport)
    c.configure_transport("streamable_http", "http://h/mcp")
    assert isinstance(c._transport, StreamableHttpTransport)
    c.configure_transport("stdio", "", stdio_command=("python", "-m", "x"))
    assert isinstance(c._transport, StdioTransport)
    with pytest.raises(ValueError, match="Unsupported remote gameplay transport"):
        c.configure_transport("carrier_pigeon", "coop")


def test_start_game_signs_and_parses(fake_client):
    msg = StartGameMessage(
        game_id="G1",
        roles={"cop": "a", "police": "b"},
        config_sha256=_SHA,
        protocol_version="1.0",
        endpoint="http://localhost:5000/mcp",
        timestamp="2026-01-01T00:00:00Z",
    )
    out = asyncio.run(_client().start_game(msg))
    assert out == {"ok": True, "phase": "commit"}
    tool, params = fake_client.calls[0]
    assert tool == "start_game"
    assert json.loads(params["message_json"])["game_id"] == "G1"
    assert len(params["signature"]) == 64


def test_action_and_ping(fake_client):
    msg = ActionMessage(
        game_id="G1",
        step=1,
        role="cop",
        config_sha256=_SHA,
        timestamp="t",
        phase="commit",
        h_commit="b" * 64,
    )
    out = asyncio.run(_client().action("G1", msg))
    assert out["ok"] is True
    assert fake_client.calls[0][1]["game_id"] == "G1"
    asyncio.run(_client().ping())
    assert fake_client.calls[1] == ("ping", {})


def test_call_tool_result_shapes(fake_client):
    c = _client()
    fake_client.result = _Result([_Text("plain text, not json")])
    assert asyncio.run(c.ping()) == {"ok": True, "raw": "plain text, not json"}
    fake_client.result = _Result([_Text("failure detail")], is_error=True)
    assert asyncio.run(c.ping()) == {"ok": False, "error": "failure detail"}
    fake_client.result = _Result([object()])
    assert asyncio.run(c.ping())["ok"] is True
    fake_client.result = _Result([], is_error=False)
    assert asyncio.run(c.ping()) == {"ok": True}
    fake_client.result = _Result([], is_error=True)
    assert asyncio.run(c.ping()) == {"ok": False}


def test_call_tool_propagates_errors(fake_client):
    fake_client.raise_exc = RuntimeError("link down")
    with pytest.raises(RuntimeError, match="link down"):
        asyncio.run(_client().ping())
