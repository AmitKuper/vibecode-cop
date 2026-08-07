"""Tests for SyntheticBeliefProvider — belief map shape and normalization."""

import numpy as np

from cop_worker.synthetic_belief import SyntheticBeliefProvider


def make_provider():
    """Return a fresh SyntheticBeliefProvider."""
    return SyntheticBeliefProvider()


def test_belief_map_shape():
    """get_belief_map must return an (N, N) array."""
    p = make_provider()
    bm = p.get_belief_map(7, (3, 3))
    assert bm.shape == (7, 7)


def test_belief_map_sums_to_one():
    """Belief map must sum to 1.0."""
    p = make_provider()
    bm = p.get_belief_map(7, (3, 3))
    assert abs(float(bm.sum()) - 1.0) < 1e-5


def test_high_confidence_peak_at_true_position():
    """High-confidence map must have max value at the true opponent position."""
    p = make_provider()
    bm = p.get_belief_map(7, (2, 4), confidence_level="high")
    peak = np.unravel_index(bm.argmax(), bm.shape)
    assert peak == (2, 4)


def test_belief_map_non_negative():
    """All belief map values must be non-negative."""
    p = make_provider()
    bm = p.get_belief_map(7, (0, 0), confidence_level="low")
    assert float(bm.min()) >= 0.0


def test_medium_confidence_returns_valid_map():
    """Medium confidence map must be valid shape and sum to 1."""
    p = make_provider()
    bm = p.get_belief_map(7, (3, 3), confidence_level="medium")
    assert bm.shape == (7, 7)
    assert abs(float(bm.sum()) - 1.0) < 1e-4


def test_reproducible_with_seeded_rng():
    """Two calls with same seeded rng must produce identical maps."""
    p = make_provider()
    rng1 = np.random.default_rng(42)
    rng2 = np.random.default_rng(42)
    bm1 = p.get_belief_map(7, (3, 3), confidence_level="low", rng=rng1)
    bm2 = p.get_belief_map(7, (3, 3), confidence_level="low", rng=rng2)
    np.testing.assert_array_equal(bm1, bm2)
