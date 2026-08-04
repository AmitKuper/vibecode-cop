"""Phase 5 v7: Tests for SafeLiveView production wiring and GameProtocolPort."""

from agent.agent_orchestrator import AgentOrchestrator
from agent.mcp.protocol_port import GameProtocolPort


def _make_orchestrator(role: str) -> AgentOrchestrator:
    return AgentOrchestrator(role=role, game_uid="test-uid", grid_size=7)


# ---------------------------------------------------------------------------
# SafeLiveView publishing
# ---------------------------------------------------------------------------


def test_publish_live_view_no_opponent_position():
    """SafeLiveView published by cop must have no opponent_position field."""
    orch = _make_orchestrator("cop")
    orch.publish_live_view(own_position=(3, 3), barriers=[])
    view = orch.live_view.get_current()
    assert view is not None
    view_dict = view.__dict__
    assert "opponent_position" not in view_dict
    assert "thief_position" not in view_dict


def test_publish_live_view_has_belief_heatmap():
    """belief_heatmap must be a list of lists of floats."""
    orch = _make_orchestrator("thief")
    orch.publish_live_view(own_position=(1, 1), barriers=[])
    view = orch.live_view.get_current()
    assert view is not None
    assert isinstance(view.belief_heatmap, list)
    assert isinstance(view.belief_heatmap[0], list)
    assert isinstance(view.belief_heatmap[0][0], float)


def test_publish_live_view_has_own_position():
    """own_position in view must match what was passed."""
    orch = _make_orchestrator("cop")
    orch.publish_live_view(own_position=(2, 4), barriers=[])
    view = orch.live_view.get_current()
    assert view is not None
    assert view.own_position == (2, 4)


def test_live_view_no_thief_position_for_cop():
    """Cop's SafeLiveView must not contain thief_position."""
    orch = _make_orchestrator("cop")
    orch.publish_live_view(own_position=(0, 0), barriers=[])
    view = orch.live_view.get_current()
    assert view is not None
    from dataclasses import asdict
    d = asdict(view)
    assert "thief_position" not in d


def test_live_view_no_cop_position_for_thief():
    """Thief's SafeLiveView must not contain cop_position."""
    orch = _make_orchestrator("thief")
    orch.publish_live_view(own_position=(6, 6), barriers=[])
    view = orch.live_view.get_current()
    assert view is not None
    from dataclasses import asdict
    d = asdict(view)
    assert "cop_position" not in d


# ---------------------------------------------------------------------------
# GameProtocolPort wiring
# ---------------------------------------------------------------------------


def test_create_protocol_port_returns_port():
    """create_protocol_port() must return a GameProtocolPort."""
    orch = _make_orchestrator("cop")
    port = orch.create_protocol_port()
    assert isinstance(port, GameProtocolPort)


def test_protocol_port_mapping_locked():
    """After create_protocol_port(), _mapping_hash must be a non-empty hex string."""
    orch = _make_orchestrator("thief")
    orch.create_protocol_port()
    assert orch._mapping_hash
    assert len(orch._mapping_hash) == 64  # sha256 hex


def test_protocol_port_stub_transport():
    """With stub_handler, the port should use StubTransportAdapter."""
    import asyncio

    async def _handler(tool_name, params):
        return {"tool": tool_name, "echo": params}

    orch = _make_orchestrator("cop")
    port = orch.create_protocol_port(stub_handler=_handler)
    assert isinstance(port, GameProtocolPort)
    # Verify stub is wired: connect and call start_game
    from agent.mcp.transport_port import StubTransportAdapter
    assert isinstance(port._transport, StubTransportAdapter)

    async def _run():
        await port._transport.connect("stub://")
        result = await port.start_game({"game_id": "x"})
        return result

    result = asyncio.run(_run())
    assert result["tool"] == "start_game"
