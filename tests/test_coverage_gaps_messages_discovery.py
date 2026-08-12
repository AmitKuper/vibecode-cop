"""Targeted tests for modules the 2026-08-10 additions left under the CI coverage gate.

This part pins the MCP message validators and protocol discovery (minus the network call).
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# cop_worker.mcp.messages — the validators
# ---------------------------------------------------------------------------
from cop_worker.mcp.messages import (
    ActionMessage,
    MessagePhase,
    StartGameMessage,
    validate_action_message,
    validate_start_game_message,
)

_SHA = "a" * 64


class TestMessageValidators:
    def test_start_game_happy_path(self) -> None:
        msg = StartGameMessage(
            game_id="g1",
            roles={"cop": "a", "police": "b"},
            config_sha256=_SHA,
            protocol_version="1.0",
            endpoint="http://localhost:5000/mcp",
            timestamp="2026-08-10T20:00:00+03:00",
        )
        assert validate_start_game_message(msg) == (True, None)

    @pytest.mark.parametrize(
        ("field", "value", "hint"),
        [
            ("game_id", "", "game_id"),
            ("roles", {"cop": "a"}, "roles"),
            ("config_sha256", "short", "config_sha256"),
            ("protocol_version", "2.0", "protocol_version"),
            ("endpoint", "not-a-url", "endpoint"),
            ("timestamp", "", "timestamp"),
        ],
    )
    def test_start_game_refusals(self, field, value, hint) -> None:
        msg = StartGameMessage(
            game_id="g1",
            roles={"cop": "a", "police": "b"},
            config_sha256=_SHA,
            protocol_version="1.0",
            endpoint="http://localhost:5000/mcp",
            timestamp="t",
        )
        setattr(msg, field, value)
        ok, err = validate_start_game_message(msg)
        assert ok is False and hint in err

    def test_action_message_happy_and_refusals(self) -> None:
        msg = ActionMessage(
            game_id="g1",
            step=1,
            role="cop",
            config_sha256=_SHA,
            timestamp="t",
            phase=MessagePhase.COMMIT.value,
            h_commit=_SHA,
        )
        assert validate_action_message(msg)[0] is True
        msg.step = -1
        assert validate_action_message(msg)[0] is False
        msg.step = 1
        msg.role = "spectator"
        assert validate_action_message(msg)[0] is False
        msg.role = "cop"
        msg.phase = "no_such_phase"
        assert validate_action_message(msg)[0] is False


# ---------------------------------------------------------------------------
# cop_worker.mcp.discovery — everything except the network call
# ---------------------------------------------------------------------------
from cop_worker.mcp.discovery import ProtocolDiscovery


class TestProtocolDiscovery:
    def test_sse_url_derivation_and_empty_state(self) -> None:
        disc = ProtocolDiscovery("http://localhost:5001/mcp")
        assert disc._sse_url == "http://localhost:5001/sse"
        assert disc.discovered is False
        assert disc.get_tool_names() == []
        assert disc.has_tool("negotiate") is False
        assert disc.get_tool_schema("negotiate") is None

    def test_validation_and_serialization_over_discovered_tools(self) -> None:
        disc = ProtocolDiscovery("http://localhost:5001/mcp")
        disc.tools = {
            "negotiate": {"name": "negotiate", "description": "", "schema": {}},
            "receive_turn": {"name": "receive_turn", "description": "", "schema": {}},
        }
        disc.discovered = True
        ok, msg = disc.validate_protocol(["negotiate", "receive_turn"])
        assert ok is True and "available" in msg
        ok, msg = disc.validate_protocol(["negotiate", "submit_audit"])
        assert ok is False and "submit_audit" in msg
        assert (
            disc.has_tool("negotiate") and disc.get_tool_schema("negotiate")["name"] == "negotiate"
        )
        serialized = disc.to_dict()
        assert serialized["discovered"] is True
        assert sorted(serialized["tools"]) == ["negotiate", "receive_turn"]

    @pytest.mark.anyio
    async def test_discover_failure_path_returns_false(self) -> None:
        # No server behind this port: the network branch must fail CLOSED (False),
        # never raise into the caller.
        disc = ProtocolDiscovery("http://127.0.0.1:9/mcp", timeout_seconds=0.5)
        assert await disc.discover() is False
        assert disc.discovered is False
