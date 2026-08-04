"""Tests for Phase 2 v7: hidden coordinate removal from production observation path.

Verifies that:
- build_local_observation() never leaks opponent coordinates
- RL tensor has no raw opponent coordinate encoding
- Orchestrator wires scent and belief correctly after turns
- apply_turn() uses the domain engine and returns correct state
"""

from __future__ import annotations

import numpy as np

from agent.observation import BeliefState, LocalObservation
from agent.peer_turn_helpers import build_local_observation
from agent.rl.local_obs_adapter import local_obs_to_tensor, obs_tensor_shape

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_scent(n: int = 7) -> list[list[float]]:
    return [[0.0] * n for _ in range(n)]


def _make_obs(role: str, own_pos: tuple, grid_size: int = 7, belief_engine=None) -> dict:
    return build_local_observation(
        role=role,
        own_position=own_pos,
        barriers=[],
        opponent_scent=_empty_scent(grid_size),
        last_hint="",
        step=1,
        gamelet=1,
        grid_size=grid_size,
        own_barriers_remaining=14 if role == "cop" else 0,
        belief_engine=belief_engine,
    )


# ---------------------------------------------------------------------------
# 2E-1: cop observation has no thief_position
# ---------------------------------------------------------------------------


class TestBuildLocalObservationCopNoThiefPosition:
    def test_build_local_observation_cop_no_thief_position(self):
        obs = _make_obs("cop", (1, 1))
        assert "thief_position" not in obs
        assert "cop_position" not in obs  # own pos is under "own_position"
        assert "own_position" in obs
        assert obs["own_position"] == (1, 1)


# ---------------------------------------------------------------------------
# 2E-2: thief observation has no cop_position
# ---------------------------------------------------------------------------


class TestBuildLocalObservationThiefNoCopPosition:
    def test_build_local_observation_thief_no_cop_position(self):
        obs = _make_obs("thief", (5, 5))
        assert "cop_position" not in obs
        assert "thief_position" not in obs
        assert "own_position" in obs
        assert obs["own_position"] == (5, 5)


# ---------------------------------------------------------------------------
# 2E-3: neither observation contains "opponent_position"
# ---------------------------------------------------------------------------


class TestBuildLocalObservationNoOpponentPosition:
    def test_build_local_observation_no_opponent_position(self):
        for role, pos in [("cop", (0, 0)), ("thief", (6, 6))]:
            obs = _make_obs(role, pos)
            assert "opponent_position" not in obs, f"opponent_position leaked for role={role}"


# ---------------------------------------------------------------------------
# 2E-4: belief_heatmap present when belief_engine provided
# ---------------------------------------------------------------------------


class TestBuildLocalObservationHasBeliefHeatmap:
    def test_build_local_observation_has_belief_heatmap(self):
        from agent.belief_engine import BeliefEngine

        be = BeliefEngine(7, "cop")
        obs = _make_obs("cop", (2, 2), belief_engine=be)
        assert "belief_heatmap" in obs
        hmap = obs["belief_heatmap"]
        assert len(hmap) == 7
        assert len(hmap[0]) == 7
        total = sum(v for row in hmap for v in row)
        assert abs(total - 1.0) < 1e-6, f"belief_heatmap doesn't sum to 1.0: {total}"

    def test_build_local_observation_no_belief_heatmap_when_none(self):
        obs = _make_obs("thief", (3, 3), belief_engine=None)
        assert "belief_heatmap" not in obs


# ---------------------------------------------------------------------------
# 2E-5: local_obs_to_tensor returns correct shape
# ---------------------------------------------------------------------------


class TestLocalObsTensorShape:
    def test_local_obs_tensor_shape(self):
        n = 7
        local_obs = LocalObservation(
            own_position=(1, 1),
            own_barriers_remaining=14,
            known_barriers=[],
            opponent_scent=_empty_scent(n),
            last_hint="",
            step=0,
            gamelet=0,
            grid_size=n,
        )
        belief = BeliefState.uniform(n)
        tensor = local_obs_to_tensor(local_obs, belief)
        expected = obs_tensor_shape(n)
        assert tensor.shape == (expected,), f"Expected shape ({expected},), got {tensor.shape}"


# ---------------------------------------------------------------------------
# 2E-6: tensor doesn't contain raw opponent coordinates
# ---------------------------------------------------------------------------


class TestLocalObsTensorNoRawCoords:
    def test_local_obs_tensor_no_raw_coords(self):
        """Passing different opponent positions (same own pos) should NOT change
        raw coordinate values in predictable tensor positions — instead the scent
        encodes the implicit location indirectly."""
        n = 7
        own_pos = (1, 1)
        belief = BeliefState.uniform(n)

        # Varying opponent scent (simulating different opponent positions)
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

        # The tensors differ (scent encodes position indirectly)
        assert not np.array_equal(tensor_a, tensor_b), (
            "Different scents should produce different tensors"
        )

        # The own-position one-hot is identical in both (index 1*7+1 = 8)
        own_oh_a = tensor_a[: n * n]
        own_oh_b = tensor_b[: n * n]
        assert own_oh_a[own_pos[0] * n + own_pos[1]] == 1.0
        assert own_oh_b[own_pos[0] * n + own_pos[1]] == 1.0
        np.testing.assert_array_equal(own_oh_a, own_oh_b)


# ---------------------------------------------------------------------------
# 2E-7: orchestrator updates scent correctly for both roles
# ---------------------------------------------------------------------------


class TestOrchestratorUpdateScentAfterTurn:
    def test_orchestrator_update_scent_after_turn(self):
        from agent.agent_orchestrator import AgentOrchestrator

        orch = AgentOrchestrator(role="cop", game_uid="test-g01", grid_size=7)
        cop_pos = (0, 0)
        thief_pos = (6, 6)
        orch.update_scent_and_belief(cop_pos, thief_pos, [])

        # Cop sees thief scent (thief was at 6,6)
        cop_scent = orch.scent_fields.cop_observation_scent()
        # Thief scent should be nonzero near (6,6)
        assert cop_scent[6][6] > 0.0, "Cop should see thief scent near (6,6)"

        # Thief sees cop scent (cop was at 0,0)
        thief_scent = orch.scent_fields.thief_observation_scent()
        assert thief_scent[0][0] > 0.0, "Thief should see cop scent near (0,0)"


# ---------------------------------------------------------------------------
# 2E-8: belief normalizes after update
# ---------------------------------------------------------------------------


class TestOrchestratorBeliefNormalizes:
    def test_orchestrator_belief_normalizes(self):
        from agent.agent_orchestrator import AgentOrchestrator

        orch = AgentOrchestrator(role="cop", game_uid="test-g02", grid_size=7)
        orch.update_scent_and_belief((0, 0), (6, 6), [])
        total = float(orch.belief_engine.belief.prob.sum())
        assert abs(total - 1.0) < 1e-5, f"Belief prob sum not 1.0: {total}"


# ---------------------------------------------------------------------------
# 2E-9: apply_turn uses domain engine
# ---------------------------------------------------------------------------


class TestApplyTurnUsesDomainEngine:
    def test_apply_turn_uses_domain_engine(self):
        from agent.agent_orchestrator import AgentOrchestrator
        from agent.domain.types import DomainState

        orch = AgentOrchestrator(role="cop", game_uid="test-g03", grid_size=7)
        state = DomainState(
            turn=0,
            grid_size=7,
            cop_position=(0, 0),
            thief_position=(6, 6),
            barriers=[],
            cop_barriers_remaining=14,
        )
        result = orch.apply_turn(state, "SOUTH", "NORTH")
        new_state = result.new_state
        # Cop moves SOUTH: (0,0) -> (0,1)
        assert new_state.cop_position == (0, 1), (
            f"Expected cop at (0,1), got {new_state.cop_position}"
        )
        # Thief moves NORTH: (6,6) -> (6,5)
        assert new_state.thief_position == (6, 5), (
            f"Expected thief at (6,5), got {new_state.thief_position}"
        )
        assert new_state.turn == 1

    def test_apply_turn_illegal_cop_action_propagates(self):
        """Illegal cop actions should NOT be silently converted to STAY in domain engine."""
        from agent.agent_orchestrator import AgentOrchestrator
        from agent.domain.types import DomainState

        orch = AgentOrchestrator(role="cop", game_uid="test-g04", grid_size=7)
        state = DomainState(
            turn=0,
            grid_size=7,
            cop_position=(0, 0),
            thief_position=(6, 6),
            barriers=[],
            cop_barriers_remaining=0,  # no barriers left
        )
        # PLACE_N with 0 barriers remaining — should return illegal cop action result
        result = orch.apply_turn(state, "PLACE_N", "STAY")
        assert not result.cop_action_legal, "Expected illegal cop action to be flagged"


# ---------------------------------------------------------------------------
# 2E-10: symmetric scent — both fields nonzero after update
# ---------------------------------------------------------------------------


class TestSymmetricScentBothFieldsUpdate:
    def test_symmetric_scent_both_fields_update(self):
        from agent.agent_orchestrator import AgentOrchestrator

        orch = AgentOrchestrator(role="thief", game_uid="test-g05", grid_size=7)
        orch.update_scent_and_belief((3, 3), (1, 1), [])

        cop_scent_arr = np.array(orch.scent_fields.cop_scent)
        thief_scent_arr = np.array(orch.scent_fields.thief_scent)

        assert cop_scent_arr.sum() > 0.0, "cop_scent field should be nonzero after update"
        assert thief_scent_arr.sum() > 0.0, "thief_scent field should be nonzero after update"
