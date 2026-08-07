"""Tests for cop_worker.gamelet — lifecycle, validation, and belief shape."""

from __future__ import annotations

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
    "setting": "Haifa",
    "hint_max_words": 15,
    "axis_origin_corner": "top-left",
    "axis_start_index": 0,
    "thief_start": [3, 3],
    "cop_start": [0, 0],
}


def _make_gamelet(**kwargs) -> Gamelet:
    """Construct a Gamelet with VALID_TERMS and sensible defaults."""
    return Gamelet(
        game_uid="test-uid-0001",
        sub_game_number=1,
        terms=kwargs.get("terms", VALID_TERMS),
        opponent_group="group-B",
        role=kwargs.get("role", "police"),
        belief_provider=SyntheticBeliefProvider(),
    )


def test_start_gamelet_validates_terms() -> None:
    """Valid terms produce a gamelet in LOCKED state."""
    g = _make_gamelet()
    assert g.state == GameletState.LOCKED


def test_start_gamelet_rejects_invalid_fixed_param() -> None:
    """smell_grid_size=3 (FIXED must be 5) raises GameletError."""
    bad_terms = {**VALID_TERMS, "smell_grid_size": 3}
    with pytest.raises(GameletError, match="Term violations"):
        _make_gamelet(terms=bad_terms)


def test_start_gamelet_rejects_below_minimum_param() -> None:
    """board_size=5 (MINIMUM must be >= 7) raises GameletError."""
    bad_terms = {**VALID_TERMS, "board_size": 5}
    with pytest.raises(GameletError, match="Term violations"):
        _make_gamelet(terms=bad_terms)


def test_prepare_audit_only_after_gameplay_terminal() -> None:
    """prepare_audit raises GameletError if not in GAMEPLAY_TERMINAL state."""
    g = _make_gamelet()
    assert g.state == GameletState.LOCKED
    with pytest.raises(GameletError, match="GAMEPLAY_TERMINAL"):
        g.prepare_audit()


def test_get_result_only_after_settled() -> None:
    """get_result raises GameletError if not in SETTLED state."""
    g = _make_gamelet()
    with pytest.raises(GameletError, match="SETTLED"):
        g.get_result()


def test_nonces_not_in_get_result() -> None:
    """get_result dict must not contain raw nonce keys."""
    g = _make_gamelet()
    g._force_state("SETTLED")
    result = g.get_result()
    assert "nonce" not in result
    assert "nonces" not in result
    assert "nonce_log" not in result


def test_belief_map_shape() -> None:
    """SyntheticBeliefProvider returns (7, 7) ndarray summing to ~1.0."""
    provider = SyntheticBeliefProvider()
    belief_map = provider.get_belief_map(board_size=7, true_opponent_position=(3, 3))
    assert belief_map.shape == (7, 7)
    assert abs(belief_map.sum() - 1.0) < 1e-5


def test_gamelet_role_is_police() -> None:
    """cop_worker gamelet always reports role='police'."""
    g = _make_gamelet()
    assert g.role == "police"


def test_shutdown_non_terminal_transitions_to_technical_failure() -> None:
    """shutdown() from LOCKED moves gamelet to TECHNICAL_FAILURE."""
    g = _make_gamelet()
    assert g.state == GameletState.LOCKED
    result = g.shutdown()
    assert result["ok"] is True
    assert g.state == GameletState.TECHNICAL_FAILURE


def test_shutdown_already_terminal_is_noop() -> None:
    """shutdown() when already terminal does not change state."""
    g = _make_gamelet()
    g._force_state("SETTLED")
    result = g.shutdown()
    assert result["ok"] is True
    assert g.state == GameletState.SETTLED


def test_start_playing_transitions_to_playing() -> None:
    """start_playing() transitions gamelet from LOCKED to PLAYING."""
    g = _make_gamelet()
    g.start_playing()
    assert g.state == GameletState.PLAYING


def test_process_event_unknown_type_raises() -> None:
    """process_event with unknown event_type raises GameletError."""
    g = _make_gamelet()
    with pytest.raises(GameletError, match="Unknown event_type"):
        g.process_event("bogus_event", {})
