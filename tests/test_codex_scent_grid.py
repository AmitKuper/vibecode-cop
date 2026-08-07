"""Tests for compute_scent_grid implementation."""

from cop_worker.scent import compute_scent_grid


def test_scent_grid_shape():
    """Output must be grid_size × grid_size."""
    grid = compute_scent_grid([3, 3], 7, 5, 0.9, 0.1)
    assert len(grid) == 5
    assert all(len(row) == 5 for row in grid)


def test_scent_center_intensity():
    """Center cell must equal emit_intensity when cop at center of board."""
    grid = compute_scent_grid([3, 3], 7, 5, 0.9, 0.1)
    center = grid[2][2]
    assert abs(center - 0.9) < 1e-4


def test_scent_decays_with_distance():
    """Cells farther from cop must have lower scent."""
    grid = compute_scent_grid([3, 3], 7, 5, 0.9, 0.1)
    center = grid[2][2]
    adjacent = grid[2][3]
    corner = grid[0][0]
    assert center > adjacent > corner


def test_scent_out_of_bounds_is_zero():
    """Cells that fall outside the board must have scent = 0.0."""
    # Cop at bottom-right corner: the grid extends past board edge
    # With board_size=5 and cop at [4,4], grid starts at max(0,4-2)=2
    # The grid covers board x=[2..6], but board ends at 4, so x=5,6 are off-board
    grid = compute_scent_grid([4, 4], 5, 5, 0.9, 0.1)
    # Last column (x=6) and second-to-last col (x=5) are off board
    assert grid[0][3] == 0.0  # x=2+3=5, off board
    assert grid[0][4] == 0.0  # x=2+4=6, off board


def test_scent_all_values_non_negative():
    """No scent value must be negative."""
    grid = compute_scent_grid([1, 1], 7, 5, 0.9, 0.1)
    for row in grid:
        for val in row:
            assert val >= 0.0


def test_scent_grid_returns_list_of_lists():
    """Return type must be list[list[float]]."""
    grid = compute_scent_grid([3, 3], 7, 5, 0.9, 0.1)
    assert isinstance(grid, list)
    assert isinstance(grid[0], list)
    assert isinstance(grid[0][0], float)
