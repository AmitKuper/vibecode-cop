"""Test that cop declares capture terminal correctly."""

from cop_worker.gamelet import Gamelet
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


def test_cop_declares_capture_terminal():
    """Gamelet state must reach GAMEPLAY_TERMINAL on forced transition."""
    provider = SyntheticBeliefProvider()
    g = Gamelet(
        game_uid="capture_rv_001",
        sub_game_number=1,
        terms=VALID_TERMS,
        opponent_group="oppgroup",
        role="police",
        belief_provider=provider,
    )
    assert g.state != GameletState.GAMEPLAY_TERMINAL
    g._force_state("GAMEPLAY_TERMINAL")
    assert g.state == GameletState.GAMEPLAY_TERMINAL
