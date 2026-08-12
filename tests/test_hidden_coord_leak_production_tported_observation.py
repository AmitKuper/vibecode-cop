"""Tests for hidden coordinate removal from production observation path.

Verifies that:
- LocalObservation never contains opponent coordinates
- BeliefState normalizes correctly after update
"""

from __future__ import annotations

import numpy as np

from cop_worker.observation import BeliefState
from tests.helpers_hidden_coord_leak import _make_obs

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
# BeliefEngine normalizes
# ---------------------------------------------------------------------------


class TestBeliefEngineNormalizes:
    def test_belief_engine_normalizes(self):
        from cop_worker.belief_engine import BeliefEngine

        engine = BeliefEngine(7, "cop")
        belief = engine.belief
        prob = np.array(belief.prob)
        assert abs(prob.sum() - 1.0) < 1e-5, f"Belief prob sum not 1.0: {prob.sum()}"
