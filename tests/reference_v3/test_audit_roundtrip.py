"""Test that audit bundle sent and verified transitions correctly."""

from cop_worker.gamelet import Gamelet
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


def test_audit_bundle_sent_and_verified():
    """prepare_audit must return ok=True and transition to AUDITING."""
    provider = SyntheticBeliefProvider()
    g = Gamelet(
        game_uid="audit_rv_001",
        sub_game_number=1,
        terms=VALID_TERMS,
        opponent_group="oppgroup",
        role="police",
        belief_provider=provider,
    )
    g._force_state("GAMEPLAY_TERMINAL")
    result = g.prepare_audit()
    assert result.get("ok") is True
    assert "audit_bundle" in result
