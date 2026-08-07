"""Tests for Phase 3B: symmetric scent fields."""

from __future__ import annotations

import numpy as np

from cop_worker.scent import KERNEL_RADIUS, ScentFields, _radial_kernel


class TestRadialKernel:
    def test_shape(self):
        k = _radial_kernel(2)
        assert k.shape == (5, 5)

    def test_center_is_max(self):
        k = _radial_kernel(2)
        center = KERNEL_RADIUS
        assert k[center][center] == max(k.flatten())

    def test_center_value(self):
        k = _radial_kernel(2)
        center = KERNEL_RADIUS
        assert abs(k[center][center] - 0.9) < 1e-9

    def test_all_non_negative(self):
        k = _radial_kernel(2)
        assert (k >= 0).all()


class TestScentFields:
    def test_zeros_init(self):
        sf = ScentFields.zeros(7)
        assert sf.cop_scent.shape == (7, 7)
        assert sf.thief_scent.shape == (7, 7)
        assert sf.cop_scent.sum() == 0.0
        assert sf.thief_scent.sum() == 0.0

    def test_update_returns_new_instance(self):
        sf = ScentFields.zeros(7)
        sf2 = sf.update((3, 3), (5, 5))
        assert sf2 is not sf

    def test_update_adds_scent_at_positions(self):
        sf = ScentFields.zeros(7)
        sf2 = sf.update((0, 0), (6, 6))
        # After update, some cells near each position should be > 0
        assert sf2.cop_scent[0][0] > 0
        assert sf2.thief_scent[6][6] > 0

    def test_decay_applied(self):
        sf = ScentFields.zeros(7)
        sf2 = sf.update((3, 3), (3, 3))
        # Decay then add: after another update at same pos, old values should be decayed
        sf3 = sf2.update((3, 3), (3, 3))
        # The center cell after 2 updates: (prev * 0.9 + kernel_center)
        # We only check that it's larger than a single emission
        kernel_center = 0.9
        assert sf3.cop_scent[3][3] > kernel_center

    def test_asymmetric_xy_position_maps_to_row_y_column_x(self):
        sf = ScentFields.zeros(7).update((1, 4), (5, 2))
        assert sf.cop_scent[4][1] == 0.9
        assert sf.thief_scent[2][5] == 0.9
        assert sf.cop_scent[1][4] < 0.9

    def test_decay_factor(self):
        sf = ScentFields.zeros(7)
        sf2 = sf.update((3, 3), (3, 3))
        center_val = sf2.cop_scent[3][3]
        # Move away so center gets only decay
        sf3 = sf2.update((0, 0), (0, 0))
        # After moving agent away, center of old pos should be decayed
        assert sf3.cop_scent[3][3] < center_val  # no new emission there

    def test_symmetric_roles(self):
        sf = ScentFields.zeros(7)
        sf2 = sf.update((1, 1), (5, 5))
        # cop scent should be non-zero near (1,1)
        assert sf2.cop_scent[1][1] > 0
        # thief scent should be non-zero near (5,5)
        assert sf2.thief_scent[5][5] > 0
        # cop scent at thief position should be minimal (not equal)
        # thief scent at cop position should be minimal
        assert sf2.cop_scent[5][5] < sf2.cop_scent[1][1]

    def test_cop_sees_thief_scent(self):
        """Cop observation returns thief scent only."""
        sf = ScentFields.zeros(7)
        sf2 = sf.update((1, 1), (5, 5))
        cop_view = sf2.cop_observation_scent()
        # cop sees thief scent
        assert cop_view[5][5] > 0
        # It should be the thief_scent grid
        assert isinstance(cop_view, list)
        assert len(cop_view) == 7
        assert len(cop_view[0]) == 7

    def test_thief_sees_cop_scent(self):
        """Thief observation returns cop scent only."""
        sf = ScentFields.zeros(7)
        sf2 = sf.update((1, 1), (5, 5))
        thief_view = sf2.thief_observation_scent()
        # thief sees cop scent — cop was at (1,1) so cop_scent[1][1] > 0
        assert thief_view[1][1] > 0
        assert isinstance(thief_view, list)

    def test_observation_scent_different(self):
        """Cop and thief views should differ when positions differ."""
        sf = ScentFields.zeros(7)
        sf2 = sf.update((1, 1), (5, 5))
        cop_view = np.array(sf2.cop_observation_scent())
        thief_view = np.array(sf2.thief_observation_scent())
        # They are NOT the same when positions differ
        assert not np.allclose(cop_view, thief_view)

    def test_boundary_positions(self):
        """Agent at corners should not raise."""
        sf = ScentFields.zeros(5)
        sf2 = sf.update((0, 0), (4, 4))
        assert sf2.cop_scent[0][0] > 0
        assert sf2.thief_scent[4][4] > 0
