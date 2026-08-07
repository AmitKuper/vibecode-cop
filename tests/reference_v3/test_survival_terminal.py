"""Test that thief declares survival terminal correctly."""
import sys
from pathlib import Path
import pytest

THIEF_REPO = Path(__file__).resolve().parents[4].parent / "vibecode-thief"
if THIEF_REPO.is_dir() and str(THIEF_REPO) not in sys.path:
    sys.path.insert(0, str(THIEF_REPO))

try:
    from thief_worker.gamelet import Gamelet as ThiefGamelet
    from thief_worker.synthetic_belief import SyntheticBeliefProvider as ThiefProvider
    HAS_THIEF = True
except ImportError:
    HAS_THIEF = False

VALID_TERMS = {
    "board_size": 7, "smell_grid_size": 5, "decay_per_step": 0.1,
    "emit_intensity": 0.9, "max_steps": 35, "survival_threshold": 35,
    "barriers_max": 14, "num_games": 6,
}


@pytest.mark.skipif(not HAS_THIEF, reason="thief_worker not on path")
def test_thief_declares_survival_at_threshold():
    """thief_worker must declare survival when step == survival_threshold."""
    provider = ThiefProvider()
    g = ThiefGamelet(
        game_uid="survival_rv_001", sub_game_number=2,
        terms=VALID_TERMS, opponent_group="oppgroup",
        role="thief", belief_provider=provider,
    )
    terminal = g.evaluate_terminal(step=35)
    assert terminal is not None
    assert terminal.result_claim == "survival"
    assert terminal.winner == "thief"
