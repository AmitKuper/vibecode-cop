"""Cover BeliefEngine.get_belief_map size handling."""

from __future__ import annotations

import numpy as np

from cop_worker.belief_engine import BeliefEngine


def test_get_belief_map_default_size_normalises_to_one():
    engine = BeliefEngine(7, "cop")
    grid = engine.get_belief_map()
    assert grid.shape == (7, 7)
    assert grid.dtype == np.float32
    assert abs(float(grid.sum()) - 1.0) < 1e-5


def test_get_belief_map_mismatched_size_returns_uniform():
    engine = BeliefEngine(7, "thief")
    grid = engine.get_belief_map(board_size=5)
    assert grid.shape == (5, 5)
    assert abs(float(grid.sum()) - 1.0) < 1e-5
    # Uniform fill: every cell identical.
    assert float(grid.min()) == float(grid.max())
