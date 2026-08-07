"""Verify the 4 ref-v3 tools are importable from league_manager.mcp_server."""

from league_manager.mcp_server import LMMCPServer


def test_four_ref_v3_tools_exposed():
    """LMMCPServer must expose negotiate, receive_turn, submit_audit, receive_control."""
    server = LMMCPServer.__new__(LMMCPServer)
    assert hasattr(server, "negotiate")
    assert hasattr(server, "receive_turn")
    assert hasattr(server, "submit_audit")
    assert hasattr(server, "receive_control")
    assert callable(server.negotiate)
    assert callable(server.receive_turn)
    assert callable(server.submit_audit)
    assert callable(server.receive_control)
