"""Tests that no hidden opponent coordinate leaks into RL tensor."""

from __future__ import annotations

from cop_worker.observation import BeliefState, LocalObservation
from cop_worker.observation_audit import audit_observation_for_leaks
from cop_worker.rl.local_obs_adapter import local_obs_to_tensor


def _make_local_obs_at(own_pos, grid_size=7) -> LocalObservation:
    scent = [[0.0] * grid_size for _ in range(grid_size)]
    return LocalObservation(
        own_position=own_pos,
        own_barriers_remaining=0,
        known_barriers=[],
        opponent_scent=scent,
        last_hint="",
        step=0,
        gamelet=0,
        grid_size=grid_size,
    )


class TestNoHiddenCoordLeak:
    def test_local_observation_has_no_opponent_position(self):
        obs = _make_local_obs_at((2, 2))
        assert not hasattr(obs, "opponent_position")

    def test_tensor_built_without_opponent_position(self):
        """Tensor should build successfully with no reference to opponent coords."""
        # Opponent's TRUE position is (6, 6) — NOT in LocalObservation
        obs = _make_local_obs_at((1, 1))
        belief = BeliefState.uniform(7)
        tensor = local_obs_to_tensor(obs, belief)
        assert tensor is not None
        assert tensor.shape[0] > 0

    def test_tensor_does_not_encode_raw_opponent_coords(self):
        """
        If opponent is at (6, 6), raw coordinates [6, 6] should NOT appear
        as the first two elements of any position-encoding sub-vector.
        The own_position one-hot at index 1*7+1=8 should be 1.0 (own pos (1,1)).
        """
        obs = _make_local_obs_at((1, 1), grid_size=7)
        belief = BeliefState.uniform(7)
        tensor = local_obs_to_tensor(obs, belief)
        n = 7
        # Own one-hot: position (1,1) = index 1*7+1 = 8
        own_oh = tensor[: n * n]
        assert own_oh[8] == 1.0, "Expected own position encoded at index 8"
        # Opponent's position (6,6) = index 6*7+6=48. It should NOT be 1.0 in own_oh
        assert own_oh[48] != 1.0

    def test_audit_catches_cop_position_in_thief_obs(self):
        """ObservationAudit must flag cop_position in grid_state for thief role."""
        obs_dict = {
            "own_position": [2, 3],
            "grid_state": {
                "thief_position": [2, 3],
                "cop_position": [5, 6],  # hidden coord leak!
                "turn": 5,
            },
        }
        leaks = audit_observation_for_leaks(obs_dict, "thief", (2, 3), (5, 6))
        assert len(leaks) > 0
        assert any("cop_position" in leak for leak in leaks)

    def test_clean_thief_obs_no_leaks(self):
        """Clean thief observation dict should produce no leaks."""
        obs_dict = {
            "own_position": [2, 3],
            "scent_field": [[0.1, 0.2], [0.3, 0.4]],
            "turn": 5,
        }
        leaks = audit_observation_for_leaks(obs_dict, "thief", (2, 3), (5, 6))
        assert leaks == []
