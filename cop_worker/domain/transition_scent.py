"""Appendix-F scent emission for the domain transition.

Split out of transition.py for the 150-line rule. This is the DOMAIN copy of the
emission law used by the local simulator; the wire law that the opponent sees
lives in rules_engine.update_scent and is the negotiated contract.
"""

from __future__ import annotations

# Mandatory scent emission kernel (Appendix-F, 5×5 radial).
# Keyed by squared Euclidean distance from emitter.
_SCENT_KERNEL: dict[int, float] = {0: 0.90, 1: 0.62, 2: 0.42, 4: 0.20, 5: 0.14, 8: 0.04}
_SCENT_DECAY = 0.9


def _update_scent(
    prev: list[list[float]],
    thief_pos: tuple[int, int],
    g: int,
) -> list[list[float]]:
    """Decay and re-emit scent according to the Appendix-F specification."""
    tx, ty = thief_pos
    grid = [[0.0] * g for _ in range(g)] if not prev else [row[:] for row in prev]
    for y in range(g):
        for x in range(g):
            dist_sq = (x - tx) ** 2 + (y - ty) ** 2
            emission = _SCENT_KERNEL.get(dist_sq, 0.0)
            grid[y][x] = round(_SCENT_DECAY * grid[y][x] + emission, 4)
    return grid
