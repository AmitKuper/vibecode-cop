"""Tests for Phase 3C: Bayesian belief engine."""

from __future__ import annotations

import numpy as np

from cop_worker.belief_engine import BeliefEngine
from cop_worker.observation import BeliefState


class TestBeliefEngineInit:
    def test_uniform_init(self):
        engine = BeliefEngine(grid_size=7, role="cop")
        assert engine.belief.prob.shape == (7, 7)
        assert abs(engine.belief.prob.sum() - 1.0) < 1e-9

    def test_role_stored(self):
        engine = BeliefEngine(grid_size=5, role="thief")
        assert engine.role == "thief"

    def test_initial_entropy_positive(self):
        engine = BeliefEngine(grid_size=5, role="cop")
        assert engine.belief.entropy > 0


class TestBeliefEnginePredict:
    def test_returns_new_engine(self):
        engine = BeliefEngine(grid_size=5, role="cop")
        engine2 = engine.predict([])
        assert engine2 is not engine

    def test_predict_sums_to_one(self):
        engine = BeliefEngine(grid_size=5, role="cop")
        engine2 = engine.predict([])
        assert abs(engine2.belief.prob.sum() - 1.0) < 1e-9

    def test_predict_with_barriers_excludes_barrier_cells(self):
        engine = BeliefEngine(grid_size=5, role="cop")
        # Fill belief at known cell
        prob = np.zeros((5, 5))
        prob[2][2] = 1.0
        engine._belief = BeliefState(5, prob, 0.0, 1.0, 0)
        # Barrier adjacent to center
        engine2 = engine.predict([(2, 3)])
        # Barrier cell should have near-zero probability
        assert engine2.belief.prob[3][2] < 1e-9

    def test_asymmetric_barrier_uses_public_xy_coordinates(self):
        engine = BeliefEngine(grid_size=5, role="cop")
        engine2 = engine.predict([(3, 1)])
        assert engine2.belief.prob[1][3] < 1e-9
        assert engine2.belief.prob[3][1] > 0

    def test_predict_spreads_probability(self):
        engine = BeliefEngine(grid_size=5, role="cop")
        # Concentrate belief at center
        prob = np.zeros((5, 5))
        prob[2][2] = 1.0
        engine._belief = BeliefState(5, prob, 0.0, 1.0, 0)
        engine2 = engine.predict([])
        # After predict, neighbor cells should also have probability
        neighbors = [(1, 2), (3, 2), (2, 1), (2, 3), (2, 2)]
        total_neighbor_prob = sum(engine2.belief.prob[r][c] for r, c in neighbors)
        assert total_neighbor_prob > 0.9


class TestBeliefEngineObserveScent:
    def test_returns_new_engine(self):
        engine = BeliefEngine(grid_size=5, role="cop")
        scent = [[0.1] * 5 for _ in range(5)]
        engine2 = engine.observe_scent(scent, [])
        assert engine2 is not engine

    def test_observe_sums_to_one(self):
        engine = BeliefEngine(grid_size=5, role="cop")
        scent = [[float(r * 5 + c) for c in range(5)] for r in range(5)]
        engine2 = engine.observe_scent(scent, [])
        assert abs(engine2.belief.prob.sum() - 1.0) < 1e-9

    def test_high_scent_increases_belief(self):
        engine = BeliefEngine(grid_size=5, role="cop")
        scent = [[0.0] * 5 for _ in range(5)]
        scent[4][4] = 10.0  # high scent at corner
        engine2 = engine.observe_scent(scent, [])
        # Belief at high-scent cell should be highest
        best_r, best_c = np.unravel_index(engine2.belief.prob.argmax(), (5, 5))
        assert (best_r, best_c) == (4, 4)

    def test_barriers_excluded_after_scent(self):
        engine = BeliefEngine(grid_size=5, role="cop")
        scent = [[1.0] * 5 for _ in range(5)]
        scent[2][2] = 100.0  # very high at barrier cell
        engine2 = engine.observe_scent(scent, [(2, 2)])
        assert engine2.belief.prob[2][2] < 1e-9


class TestBeliefEngineStepComplete:
    def test_step_updated(self):
        engine = BeliefEngine(grid_size=5, role="cop")
        engine2 = engine.step_complete(42)
        assert engine2.belief.step == 42

    def test_prob_unchanged(self):
        engine = BeliefEngine(grid_size=5, role="cop")
        engine2 = engine.step_complete(10)
        np.testing.assert_array_almost_equal(engine.belief.prob, engine2.belief.prob)


class TestBeliefStateMath:
    def test_entropy_decreases_with_concentration(self):
        prob_spread = np.ones((5, 5)) / 25
        bs_spread = BeliefState(5, prob_spread, 0.0, 0.0, 0).normalize()

        prob_concentrated = np.zeros((5, 5))
        prob_concentrated[2][2] = 1.0
        bs_concentrated = BeliefState(5, prob_concentrated, 0.0, 0.0, 0).normalize()

        assert bs_concentrated.entropy < bs_spread.entropy

    def test_confidence_increases_with_concentration(self):
        prob_spread = np.ones((5, 5)) / 25
        bs_spread = BeliefState(5, prob_spread, 0.0, 0.0, 0).normalize()

        prob_concentrated = np.zeros((5, 5))
        prob_concentrated[2][2] = 1.0
        bs_concentrated = BeliefState(5, prob_concentrated, 0.0, 0.0, 0).normalize()

        assert bs_concentrated.confidence > bs_spread.confidence
