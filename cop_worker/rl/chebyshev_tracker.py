"""Exact opponent tracking from a subtractive-chebyshev scent frame.

Under ``subtractive_chebyshev_v1`` the transmitted frame has a UNIQUE peak at the
emitter's current cell: emission merges by max (centre 0.9) and then everything decays
0.1, so the fresh centre reads 0.8 while any older peak has decayed to <= 0.7. The
argmax of every well-formed frame therefore IS the opponent's cell — the field is a
position oracle, not a probability cloud. (A peer on the 0.9-peak "fresh deposit"
convention — the league's other reading of the locked doc — yields the same argmax.)

``exact_opponent_cell`` returns the cell in (x, y) form, or None when the frame is
missing/malformed/ambiguous — callers fall back to the RL policy or last-known cell.
"""

from __future__ import annotations

_PEAKS = (0.9, 0.8)  # fresh-deposit convention / after-one-decay convention
_TOL = 1e-6


def exact_opponent_cell(
    scent_grid: list[list[float]] | None, grid_size: int
) -> tuple[int, int] | None:
    """The emitter's current cell from an NxN rendered frame, or None if not provable."""
    if not scent_grid:
        return None
    best_val = 0.0
    best_cells: list[tuple[int, int]] = []
    for r in range(min(grid_size, len(scent_grid))):
        row = scent_grid[r]
        for c in range(min(grid_size, len(row))):
            v = float(row[c])
            if v > best_val + _TOL:
                best_val, best_cells = v, [(r, c)]
            elif abs(v - best_val) <= _TOL and v > 0.0:
                best_cells.append((r, c))
    if len(best_cells) != 1:
        return None
    if not any(abs(best_val - p) <= _TOL for p in _PEAKS):
        return None
    r, c = best_cells[0]
    return (c, r)  # grid is row-major [row][col]; positions travel as (x, y)
