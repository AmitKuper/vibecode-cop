"""Coverage of the MCP server wiring and tool registration."""

from __future__ import annotations

from cop_worker.mcp.server_tools_game import register_game_tools
from cop_worker.mcp.server_tools_info import register_info_tools
from cop_worker.mcp.server_tools_probe import register_conformance_tool


class _StubMCP:
    """Captures functions registered via @mcp.tool()."""

    def __init__(self):
        self.tools = {}

    def tool(self):
        def _decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return _decorator


def test_info_tools_report_role_and_config():
    mcp = _StubMCP()
    register_info_tools(mcp, role="cop", config_sha256="c" * 64)
    assert mcp.tools["ping"]() == {"ok": True, "role": "cop"}
    cfg = mcp.tools["get_config"]()
    assert cfg["config_sha256"] == "c" * 64


def test_probe_tool_happy_and_reject_paths():
    mcp = _StubMCP()
    register_conformance_tool(mcp)
    probe = mcp.tools["protocol_conformance"]
    ok = probe("commit", "PROBE_GAME_1234", "a" * 64, "k" * 16)
    assert ok["ok"] and ok["idempotent"] and ok["side_effects"] == 0
    again = probe("commit", "PROBE_GAME_1234", "a" * 64, "k" * 16)
    assert again["semantic_digest"] == ok["semantic_digest"]
    conflict = probe("reveal", "PROBE_GAME_1234", "b" * 64, "k" * 16)
    assert conflict["ok"] is False and "idempotency" in conflict["error"]
    assert probe("commit", "REALGAME", "a" * 64, "k" * 16)["ok"] is False
    assert probe("nope", "PROBE_GAME_1", "a" * 64, "k" * 16)["ok"] is False
    assert probe("commit", "PROBE_GAME_1", "short", "k" * 16)["ok"] is False


def test_game_tools_delegate_to_handlers(monkeypatch, tmp_path):
    seen = {}

    def _fake_start(*a):
        seen["start"] = a
        return {"ok": True}

    def _fake_action(*a):
        seen["action"] = a
        return {"ok": True}

    monkeypatch.setattr("cop_worker.mcp.server_tools_game.handle_start_game", _fake_start)
    monkeypatch.setattr("cop_worker.mcp.server_tools_game.handle_action", _fake_action)
    mcp = _StubMCP()
    register_game_tools(mcp, "cop", "secret", "c" * 64, tmp_path, {}, {})
    assert mcp.tools["start_game"]("{}", "s" * 64)["ok"]
    assert mcp.tools["action"]("gid", "{}", "s" * 64)["ok"]
    assert "start" in seen and "action" in seen


def test_agent_mcp_server_registers_all_tools(tmp_path):
    from cop_worker.mcp.server import AgentMCPServer

    server = AgentMCPServer(
        role="cop",
        secret="secret",
        config_sha256="c" * 64,
        games_dir=tmp_path,
    )
    assert server.get_game_log("missing") is None
