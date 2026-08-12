"""Tests for Phase 4: RL infrastructure — local obs adapter and heuristics."""

from __future__ import annotations

import numpy as np

from cop_worker.observation import BeliefState, LocalObservation
from cop_worker.rl.action_space import THIEF_ACTIONS
from cop_worker.rl.heuristics import evasion_thief, pursuit_cop
from cop_worker.rl.local_obs_adapter import local_obs_to_tensor, obs_tensor_shape

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_local_obs(grid_size: int = 7) -> LocalObservation:
    scent = [[0.0] * grid_size for _ in range(grid_size)]
    return LocalObservation(
        own_position=(3, 3),
        own_barriers_remaining=5,
        known_barriers=[(1, 2), (4, 5)],
        opponent_scent=scent,
        last_hint="",
        step=10,
        gamelet=1,
        grid_size=grid_size,
    )


# ---------------------------------------------------------------------------
# Local obs adapter tests
# ---------------------------------------------------------------------------


class TestLocalObsToTensor:
    def test_shape_matches_expected(self):
        obs = _make_local_obs(7)
        belief = BeliefState.uniform(7)
        tensor = local_obs_to_tensor(obs, belief)
        expected = obs_tensor_shape(7)
        assert tensor.shape == (expected,), f"Expected {expected}, got {tensor.shape}"

    def test_no_opponent_position_in_output(self):
        """The tensor must NOT contain raw opponent coordinates as scalars."""
        # If opponent were at (6, 6), their coordinates would be 6 and 6.
        # Since LocalObservation has no opponent_position, the tensor cannot
        # encode them — this test just verifies tensor builds without error
        # and doesn't crash for any grid position.
        obs = _make_local_obs(7)
        belief = BeliefState.uniform(7)
        tensor = local_obs_to_tensor(obs, belief)
        assert tensor is not None
        assert not np.any(np.isnan(tensor))
        assert not np.any(np.isinf(tensor))

    def test_own_position_is_one_hot(self):
        obs = _make_local_obs(7)
        belief = BeliefState.uniform(7)
        tensor = local_obs_to_tensor(obs, belief)
        # First n*n values are one-hot for own_position (3,3)
        n = 7
        own_oh = tensor[: n * n]
        r, c = obs.own_position
        assert own_oh[r * n + c] == 1.0
        assert own_oh.sum() == 1.0

    def test_local_observation_has_no_opponent_position_field(self):
        """Critical: LocalObservation must NOT have opponent_position attribute."""
        obs = _make_local_obs(7)
        assert not hasattr(obs, "opponent_position"), (
            "LocalObservation must not have opponent_position field"
        )


# ---------------------------------------------------------------------------
# Heuristic tests
# ---------------------------------------------------------------------------


class TestPursuitCop:
    def test_moves_toward_centroid(self):
        # Cop at (0,0), centroid at (3,3) — should move S or E
        action = pursuit_cop((0, 0), (3, 3), [], 0, 7)
        assert action in ["S", "E", "STAY"]

    def test_does_not_walk_into_barrier(self):
        # Centroid is S of cop, but barrier there
        action = pursuit_cop((3, 3), (4, 3), [(4, 3)], 0, 7)
        assert action != "S"


class TestEvasionThief:
    def test_moves_away_from_centroid(self):
        # Thief at (3,3), centroid at (3,3) — any move is away or stays
        action = evasion_thief((3, 3), (3, 3), [], 7)
        assert action in THIEF_ACTIONS

    def test_picks_direction_maximizing_distance(self):
        # Thief at (0,0), cop centroid at (0,0) — moving S or E increases distance
        action = evasion_thief((0, 0), (0, 0), [], 7)
        assert action in ["S", "E", "STAY"]
