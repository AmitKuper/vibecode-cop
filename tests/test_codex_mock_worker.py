"""Tests for MockWorker — verifies the test double behaves correctly."""

from league_manager.tests.mock_worker import MockWorker

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


def make_worker(role="police"):
    """Return a fresh MockWorker."""
    return MockWorker(role=role)


def test_start_gamelet_records_call():
    """start_gamelet must record a call entry."""
    w = make_worker()
    w.start_gamelet("uid_mw_001", 1, VALID_TERMS, "peer", "police")
    w.assert_called("start_gamelet")


def test_get_status_returns_role():
    """get_status must return the configured role."""
    w = make_worker(role="thief")
    w.start_gamelet("uid_mw_002", 1, VALID_TERMS, "peer", "thief")
    status = w.get_status("uid_mw_002", 1)
    assert status["role"] == "thief"


def test_get_result_has_llm_tokens():
    """get_result must include 'llm_tokens' key."""
    w = make_worker()
    result = w.get_result("uid_mw_003", 1)
    assert "llm_tokens" in result


def test_shutdown_returns_ok():
    """shutdown_gamelet must return {'ok': True}."""
    w = make_worker()
    result = w.shutdown_gamelet("uid_mw_004", 1)
    assert result["ok"] is True


def test_reset_clears_calls():
    """reset must clear all call history."""
    w = make_worker()
    w.start_gamelet("uid_mw_005", 1, VALID_TERMS, "peer", "police")
    w.reset()
    assert w.calls == []


def test_deliver_event_records_call():
    """deliver_event must record a call entry."""
    w = make_worker()
    w.deliver_event("uid_mw_006", 1, "opponent_turn", {})
    w.assert_called("deliver_event")
