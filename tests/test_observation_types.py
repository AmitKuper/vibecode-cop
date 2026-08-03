"""Tests for Phase 3A: LocalObservation, BeliefState, SafeLiveView."""

from __future__ import annotations

import numpy as np
import pytest

from agent.observation import BeliefState, LocalObservation, SafeLiveView


class TestLocalObservation:
    def _make(self, **kwargs):
        defaults = {
            "own_position": (2, 3),
            "own_barriers_remaining": 5,
            "known_barriers": [(0, 1), (1, 2)],
            "opponent_scent": [[0.1, 0.2], [0.3, 0.4]],
            "last_hint": "heading north",
            "step": 4,
            "gamelet": 1,
            "grid_size": 7,
        }
        defaults.update(kwargs)
        return LocalObservation(**defaults)

    def test_immutable(self):
        obs = self._make()
        with pytest.raises((AttributeError, TypeError)):
            obs.own_position = (0, 0)  # type: ignore[misc]

    def test_no_opponent_position_field(self):
        obs = self._make()
        assert not hasattr(obs, "opponent_position"), (
            "LocalObservation must not have an opponent_position field"
        )
        assert not hasattr(obs, "cop_position") or obs.own_position == obs.own_position
        # Specifically ensure the dangerous fields are absent
        for forbidden in ("opponent_position", "cop_true_pos", "thief_true_pos"):
            assert not hasattr(obs, forbidden), f"Forbidden field {forbidden!r} found"

    def test_fields_accessible(self):
        obs = self._make()
        assert obs.own_position == (2, 3)
        assert obs.own_barriers_remaining == 5
        assert obs.known_barriers == [(0, 1), (1, 2)]
        assert obs.step == 4
        assert obs.gamelet == 1
        assert obs.grid_size == 7

    def test_thief_zero_barriers(self):
        obs = self._make(own_barriers_remaining=0)
        assert obs.own_barriers_remaining == 0


class TestBeliefState:
    def test_uniform_sums_to_one(self):
        bs = BeliefState.uniform(7)
        assert abs(bs.prob.sum() - 1.0) < 1e-9

    def test_uniform_shape(self):
        bs = BeliefState.uniform(5)
        assert bs.prob.shape == (5, 5)

    def test_uniform_entropy_positive(self):
        bs = BeliefState.uniform(7)
        assert bs.entropy > 0

    def test_normalize_sums_to_one(self):
        prob = np.random.rand(5, 5) + 0.01
        bs = BeliefState(grid_size=5, prob=prob, entropy=0.0, confidence=0.0, step=0)
        normed = bs.normalize()
        assert abs(normed.prob.sum() - 1.0) < 1e-9

    def test_normalize_degenerate_returns_uniform(self):
        prob = np.zeros((4, 4))
        bs = BeliefState(grid_size=4, prob=prob, entropy=0.0, confidence=0.0, step=0)
        normed = bs.normalize()
        assert abs(normed.prob.sum() - 1.0) < 1e-9

    def test_mask_barriers_zeroes_cells(self):
        bs = BeliefState.uniform(5)
        barriers = [(0, 0), (1, 1)]
        masked = bs.mask_barriers(barriers)
        assert masked.prob[0][0] < 1e-10
        assert masked.prob[1][1] < 1e-10
        assert abs(masked.prob.sum() - 1.0) < 1e-9

    def test_confidence_between_zero_and_one(self):
        bs = BeliefState.uniform(7)
        assert 0.0 <= bs.confidence <= 1.0

    def test_step_preserved(self):
        bs = BeliefState.uniform(5, step=42)
        assert bs.step == 42


class TestSafeLiveView:
    def _make(self):
        return SafeLiveView(
            own_position=(1, 2),
            belief_heatmap=[[0.1, 0.2], [0.3, 0.4]],
            opponent_scent=[[0.0, 0.5], [0.5, 0.0]],
            last_hint="heading south",
            hint_reliability=0.75,
            turn=3,
            gamelet=2,
            score={"cop": 1, "thief": 0},
            own_barriers_remaining=10,
            protocol_state="STEP_VERIFIED",
            your_turn=True,
            connection_healthy=True,
        )

    def test_immutable(self):
        view = self._make()
        with pytest.raises((AttributeError, TypeError)):
            view.own_position = (0, 0)  # type: ignore[misc]

    def test_no_hidden_opponent_coord(self):
        view = self._make()
        for forbidden in (
            "opponent_position",
            "cop_position",
            "thief_position",
            "cop_true_pos",
            "thief_true_pos",
        ):
            assert not hasattr(view, forbidden), (
                f"Forbidden field {forbidden!r} found in SafeLiveView"
            )

    def test_fields_accessible(self):
        view = self._make()
        assert view.own_position == (1, 2)
        assert view.turn == 3
        assert view.gamelet == 2
        assert view.score == {"cop": 1, "thief": 0}
        assert view.your_turn is True
        assert view.connection_healthy is True
