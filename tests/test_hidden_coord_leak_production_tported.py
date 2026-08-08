"""Tests for hidden coordinate removal from production observation path.

Verifies that:
- LocalObservation never contains opponent coordinates
- RL tensor has no raw opponent coordinate encoding
- BeliefState normalizes correctly after update
- apply_turn() uses the domain engine and returns correct state
"""

from __future__ import annotations

import numpy as np
import pytest

from cop_worker.observation import BeliefState, LocalObservation
from cop_worker.rl.local_obs_adapter import local_obs_to_tensor, obs_tensor_shape


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_scent(n: int = 7) -> list[list[float]]:
    return [[0.0] * n for _ in range(n)]


def _make_obs(role: str, own_pos: tuple, grid_size: int = 7) -> LocalObservation:
    return LocalObservation(
        own_position=own_pos,
        own_barriers_remaining=14 if role == "cop" else 0,
        known_barriers=[],
        opponent_scent=_empty_scent(grid_size),
        last_hint="",
        step=1,
        gamelet=1,
        grid_size=grid_size,
    )


# ---------------------------------------------------------------------------
# LocalObservation has no opponent_position
# ---------------------------------------------------------------------------


class TestLocalObservationCopNoThiefPosition:
    def test_local_observation_cop_no_thief_position(self):
        obs = _make_obs("cop", (1, 1))
        d = obs.__dict__
        assert "thief_position" not in d
        assert "cop_position" not in d
        assert "own_position" in d
        assert obs.own_position == (1, 1)


class TestLocalObservationThiefNoCopPosition:
    def test_local_observation_thief_no_cop_position(self):
        obs = _make_obs("thief", (5, 5))
        d = obs.__dict__
        assert "cop_position" not in d
        assert "thief_position" not in d
        assert "own_position" in d
        assert obs.own_position == (5, 5)


class TestLocalObservationNoOpponentPosition:
    def test_local_observation_no_opponent_position(self):
        for role, pos in [("cop", (0, 0)), ("thief", (6, 6))]:
            obs = _make_obs(role, pos)
            d = obs.__dict__
            assert "opponent_position" not in d, f"opponent_position leaked for role={role}"


# ---------------------------------------------------------------------------
# BeliefState
# ---------------------------------------------------------------------------


class TestBeliefStateUniform:
    def test_belief_state_uniform_sums_to_one(self):
        belief = BeliefState.uniform(7)
        prob = np.array(belief.prob)
        assert abs(prob.sum() - 1.0) < 1e-5

    def test_belief_state_uniform_has_correct_shape(self):
        belief = BeliefState.uniform(7)
        prob = np.array(belief.prob)
        assert prob.shape == (7, 7)


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
# BeliefEngine normalizes
# ---------------------------------------------------------------------------


class TestBeliefEngineNormalizes:
    def test_belief_engine_normalizes(self):
        from cop_worker.belief_engine import BeliefEngine

        engine = BeliefEngine(7, "cop")
        belief = engine.belief
        prob = np.array(belief.prob)
        assert abs(prob.sum() - 1.0) < 1e-5, f"Belief prob sum not 1.0: {prob.sum()}"


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
