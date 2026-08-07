"""Tests for cop_worker.mcp_server — 6 MCP tools called in-process."""

from __future__ import annotations

import pytest

import cop_worker.mcp_server as server
from cop_worker.gamelet import GameletError
from cop_worker.state_machine import GameletState

VALID_TERMS = {
    "board_size": 7,
    "smell_grid_size": 5,
    "decay_per_step": 0.1,
    "emit_intensity": 0.9,
    "max_steps": 35,
    "survival_threshold": 35,
    "barriers_max": 14,
    "num_games": 6,
    "setting": "Haifa",
    "hint_max_words": 15,
    "axis_origin_corner": "top-left",
    "axis_start_index": 0,
    "thief_start": [3, 3],
    "cop_start": [0, 0],
}


@pytest.fixture(autouse=True)
def clear_registry():
    """Clear gamelet registry before and after each test."""
    server.clear_all_gamelets()
    yield
    server.clear_all_gamelets()


def _uid(suffix: str) -> str:
    """Generate a unique game_uid for a test."""
    return f"test-game-{suffix}"


def test_start_gamelet_tool() -> None:
    """start_gamelet returns {'ok': True} for valid inputs."""
    result = server.start_gamelet(
        game_uid=_uid("001"),
        sub_game_number=1,
        terms=VALID_TERMS,
        opponent_group="group-B",
        role="police",
    )
    assert result == {"ok": True}


def test_duplicate_start_raises() -> None:
    """Starting the same game_uid+sub_game_number twice raises GameletError."""
    uid = _uid("002")
    server.start_gamelet(uid, 1, VALID_TERMS, "group-B", "police")
    with pytest.raises(GameletError, match="already exists"):
        server.start_gamelet(uid, 1, VALID_TERMS, "group-B", "police")


def test_get_status_tool() -> None:
    """get_status returns dict with state, step, and role keys."""
    uid = _uid("003")
    server.start_gamelet(uid, 1, VALID_TERMS, "group-B", "police")
    status = server.get_status(uid, 1)
    assert "state" in status
    assert "step" in status
    assert "role" in status
    assert status["role"] == "police"
    assert status["state"] == GameletState.LOCKED


def test_deliver_event_commit() -> None:
    """deliver_event with opponent_turn+commit kind returns ok and ack."""
    uid = _uid("004")
    server.start_gamelet(uid, 1, VALID_TERMS, "group-B", "police")
    # Transition to PLAYING so turn events are accepted
    gamelet = server._get(uid, 1)
    gamelet.start_playing()

    payload = {"kind": "commit", "step": 1, "commitment_hash": "abc123" * 10 + "ab"}
    result = server.deliver_event(uid, 1, "opponent_turn", payload)
    assert result["ok"] is True
    assert "response_payload" in result


def test_shutdown_gamelet_tool() -> None:
    """shutdown_gamelet returns ok and final_state, then removes from registry."""
    uid = _uid("005")
    server.start_gamelet(uid, 1, VALID_TERMS, "group-B", "police")
    result = server.shutdown_gamelet(uid, 1)
    assert result["ok"] is True
    assert "final_state" in result
    # Gamelet should be removed from registry after shutdown
    with pytest.raises(GameletError):
        server.get_status(uid, 1)


def test_get_unknown_gamelet_raises() -> None:
    """get_status on an unknown game_uid raises GameletError."""
    with pytest.raises(GameletError, match="No gamelet found"):
        server.get_status("nonexistent-uid", 99)


def test_start_multiple_sub_games_same_uid() -> None:
    """Different sub_game_numbers for the same game_uid are independent."""
    uid = _uid("006")
    server.start_gamelet(uid, 1, VALID_TERMS, "group-B", "police")
    server.start_gamelet(uid, 2, VALID_TERMS, "group-B", "police")
    assert server.get_status(uid, 1)["sub_game_number"] == 1
    assert server.get_status(uid, 2)["sub_game_number"] == 2


def test_get_result_before_settled_raises() -> None:
    """get_result raises GameletError if gamelet is not in SETTLED state."""
    uid = _uid("007")
    server.start_gamelet(uid, 1, VALID_TERMS, "group-B", "police")
    with pytest.raises(GameletError, match="SETTLED"):
        server.get_result(uid, 1)


def test_prepare_audit_before_gameplay_terminal_raises() -> None:
    """prepare_audit raises GameletError if not in GAMEPLAY_TERMINAL state."""
    uid = _uid("008")
    server.start_gamelet(uid, 1, VALID_TERMS, "group-B", "police")
    with pytest.raises(GameletError, match="GAMEPLAY_TERMINAL"):
        server.prepare_audit(uid, 1)
