"""Shared wire-law reproduction for the scent-decoder tests.

``_wire_step`` deliberately re-implements the negotiated ``multiplicative_book_v1``
accumulation from ``RulesEngine`` instead of calling the decoder's own helpers, so a
change to either side breaks the tests instead of cancelling out.
"""

from __future__ import annotations

import numpy as np

from cop_worker.rules_engine import RulesEngine

GRID = 7


def _wire_step(field: np.ndarray, emitter: tuple[int, int]) -> np.ndarray:
    """clamp(0.9*old + kernel, 0, 0.9) -- RulesEngine.update_scent, written out."""
    kernel = RulesEngine._SCENT_KERNEL
    px, py = emitter
    out = field.copy()
    for y in range(GRID):
        for x in range(GRID):
            emission = kernel.get((x - px) ** 2 + (y - py) ** 2, 0.0)
            out[y][x] = min(0.9, max(0.0, 0.9 * out[y][x] + emission))
    return out
