"""Test that thief declares survival terminal correctly (thief_worker)."""

import pytest


def test_thief_declares_survival_at_threshold():
    """thief_worker must declare survival when step == survival_threshold."""
    try:
        import sys

        sys.path.insert(
            0,
            "D:/studies/AI_Agent_Orchestration_Course/submission_project/vibecode-thief",
        )
        from thief_worker.gamelet import Gamelet as ThiefGamelet
        from thief_worker.synthetic_belief import SyntheticBeliefProvider as ThiefProvider

        terms = {
            "board_size": 7,
            "smell_grid_size": 5,
            "decay_per_step": 0.1,
            "emit_intensity": 0.9,
            "max_steps": 35,
            "survival_threshold": 35,
            "barriers_max": 14,
            "num_games": 6,
        }
        provider = ThiefProvider()
        g = ThiefGamelet(
            game_uid="survival_rv_001",
            sub_game_number=2,
            terms=terms,
            opponent_group="oppgroup",
            role="thief",
            belief_provider=provider,
        )
        terminal = g.evaluate_terminal(step=35)
        assert terminal is not None
        assert terminal.result_claim == "survival"
        assert terminal.winner == "thief"
    except ImportError as e:
        pytest.skip(f"thief_worker not on path: {e}")
