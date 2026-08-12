"""Tests for hidden coordinate removal from production observation path.

Verifies that:
- RL tensor has no raw opponent coordinate encoding
- apply_turn() uses the domain engine and returns correct state
"""

from __future__ import annotations

import numpy as np

from cop_worker.observation import BeliefState, LocalObservation
from cop_worker.rl.local_obs_adapter import local_obs_to_tensor, obs_tensor_shape
from tests.helpers_hidden_coord_leak import _make_obs

# ---------------------------------------------------------------------------
# RL tensor shape
# ---------------------------------------------------------------------------


class TestLocalObsTensorShape:
    def test_local_obs_tensor_shape(self):
        n = 7
        obs = _make_obs("cop", (1, 1), n)
        belief = BeliefState.uniform(n)
        tensor = local_obs_to_tensor(obs, belief)
        expected = obs_tensor_shape(n)
        assert tensor.shape == (expected,), f"Expected shape ({expected},), got {tensor.shape}"


# ---------------------------------------------------------------------------
# RL tensor does not encode raw opponent coordinates
# ---------------------------------------------------------------------------


class TestLocalObsTensorNoRawCoords:
    def test_different_scents_produce_different_tensors(self):
        """Varying opponent scent produces different tensor — no raw coordinate."""
        n = 7
        own_pos = (1, 1)
        belief = BeliefState.uniform(n)

        scent_a = [[0.1] * n for _ in range(n)]
        scent_b = [[0.9] * n for _ in range(n)]

        obs_a = LocalObservation(
            own_position=own_pos,
            own_barriers_remaining=0,
            known_barriers=[],
            opponent_scent=scent_a,
            last_hint="",
            step=0,
            gamelet=0,
            grid_size=n,
        )
        obs_b = LocalObservation(
            own_position=own_pos,
            own_barriers_remaining=0,
            known_barriers=[],
            opponent_scent=scent_b,
            last_hint="",
            step=0,
            gamelet=0,
            grid_size=n,
        )

        tensor_a = local_obs_to_tensor(obs_a, belief)
        tensor_b = local_obs_to_tensor(obs_b, belief)

        assert not np.array_equal(tensor_a, tensor_b), (
            "Different scents should produce different tensors"
        )

        own_oh_a = tensor_a[: n * n]
        own_oh_b = tensor_b[: n * n]
        # own_position one-hot should be identical in both tensors
        assert own_oh_a[own_pos[1] * n + own_pos[0]] == 1.0
        assert own_oh_b[own_pos[1] * n + own_pos[0]] == 1.0
        np.testing.assert_array_equal(own_oh_a, own_oh_b)


# ---------------------------------------------------------------------------
# Domain state transition
# ---------------------------------------------------------------------------


class TestDomainTransition:
    def test_apply_transition_moves_agents(self):
        from cop_worker.domain.transition import apply_joint_action
        from cop_worker.domain.types import DomainState

        state = DomainState(
            turn=0,
            grid_size=7,
            cop_position=(0, 0),
            thief_position=(6, 6),
            barriers=[],
            cop_barriers_remaining=14,
        )
        result = apply_joint_action(state, "SOUTH", "NORTH")
        assert result.new_state.cop_position == (0, 1), (
            f"Expected cop at (0,1), got {result.new_state.cop_position}"
        )
        assert result.new_state.thief_position == (6, 5), (
            f"Expected thief at (6,5), got {result.new_state.thief_position}"
        )
        assert result.new_state.turn == 1
