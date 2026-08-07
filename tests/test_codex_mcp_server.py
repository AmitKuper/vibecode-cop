"""Tests for cop_worker MCP server 6-tool surface."""

import pytest

from cop_worker import mcp_server as ms
from cop_worker.gamelet import GameletError

VALID_TERMS = {
    "board_size": 7,
    "smell_grid_size": 5,
    "decay_per_step": 0.1,
    "emit_intensity": 0.9,
    "max_steps": 35,
    "survival_threshold": 35,
    "barriers_max": 14,
    "num_games": 6,
}


def setup_function():
    """Clear registry before each test."""
    ms.clear_all_gamelets()


def test_start_gamelet_returns_ok():
    """start_gamelet must return {'ok': True}."""
    result = ms.start_gamelet("uid_mcp_001", 1, VALID_TERMS, "peer", "police")
    assert result["ok"] is True


def test_duplicate_start_gamelet_raises():
    """Starting the same gamelet twice must raise GameletError."""
    ms.start_gamelet("uid_mcp_002", 1, VALID_TERMS, "peer", "police")
    with pytest.raises(GameletError):
        ms.start_gamelet("uid_mcp_002", 1, VALID_TERMS, "peer", "police")


def test_get_status_returns_state():
    """get_status must return state and role."""
    ms.start_gamelet("uid_mcp_003", 1, VALID_TERMS, "peer", "police")
    status = ms.get_status("uid_mcp_003", 1)
    assert status["state"] is not None
    assert status["role"] == "police"


def test_shutdown_gamelet_removes_from_registry():
    """After shutdown, get_status must raise GameletError."""
    ms.start_gamelet("uid_mcp_004", 1, VALID_TERMS, "peer", "police")
    ms.shutdown_gamelet("uid_mcp_004", 1)
    with pytest.raises(GameletError):
        ms.get_status("uid_mcp_004", 1)


def test_get_missing_gamelet_raises():
    """get_status for nonexistent gamelet must raise GameletError."""
    with pytest.raises(GameletError):
        ms.get_status("NONEXISTENT", 1)


def test_clear_all_gamelets_empties_registry():
    """clear_all_gamelets must leave registry empty."""
    ms.start_gamelet("uid_mcp_005", 1, VALID_TERMS, "peer", "police")
    ms.clear_all_gamelets()
    with pytest.raises(GameletError):
        ms.get_status("uid_mcp_005", 1)
