"""Tests for Gamelet full lifecycle including _force_state and get_result."""

import pytest

from cop_worker.gamelet import Gamelet, GameletError
from cop_worker.state_machine import GameletState
from cop_worker.synthetic_belief import SyntheticBeliefProvider

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


def make_gamelet(role="police", sg=1, uid="g001"):
    """Create a fresh Gamelet with SyntheticBeliefProvider."""
    return Gamelet(
        game_uid=uid,
        sub_game_number=sg,
        terms=VALID_TERMS,
        opponent_group="peer",
        role=role,
        belief_provider=SyntheticBeliefProvider(),
    )


def test_gamelet_starts_in_locked_state():
    """After construction, gamelet must be in LOCKED state."""
    g = make_gamelet()
    assert g.state == GameletState.LOCKED


def test_force_state_to_gameplay_terminal():
    """_force_state must change gamelet to GAMEPLAY_TERMINAL."""
    g = make_gamelet()
    g._force_state("GAMEPLAY_TERMINAL")
    assert g.state == GameletState.GAMEPLAY_TERMINAL


def test_force_state_to_settled_provides_result():
    """_force_state to SETTLED must auto-populate a result dict."""
    g = make_gamelet()
    g._force_state("SETTLED")
    result = g.get_result()
    assert isinstance(result, dict)
    assert "game_uid" in result


def test_get_result_raises_if_not_settled():
    """get_result before SETTLED must raise GameletError."""
    g = make_gamelet()
    with pytest.raises(GameletError):
        g.get_result()


def test_result_has_llm_tokens_field():
    """get_result must include 'llm_tokens' key."""
    g = make_gamelet()
    g._force_state("SETTLED")
    result = g.get_result()
    assert "llm_tokens" in result


def test_prepare_audit_requires_gameplay_terminal():
    """prepare_audit in LOCKED state must raise GameletError."""
    g = make_gamelet()
    with pytest.raises(GameletError):
        g.prepare_audit()


def test_shutdown_from_locked_returns_technical_failure():
    """shutdown() from LOCKED sets TECHNICAL_FAILURE."""
    g = make_gamelet()
    result = g.shutdown()
    assert result["ok"] is True
    assert "TECHNICAL_FAILURE" in str(result["final_state"])
