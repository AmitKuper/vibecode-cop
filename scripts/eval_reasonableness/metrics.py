"""Scent-field readings and cross-game aggregation for the move audit."""

from __future__ import annotations

import numpy as np

_DELTA = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0), "STAY": (0, 0)}


def _scent_argmax(grid) -> tuple[int, int] | None:
    """Return (x, y) of the strongest scent cell, or None if the field is flat/empty."""
    arr = np.array(grid, dtype=float)
    if arr.size == 0 or float(arr.max()) <= 0.0:
        return None
    r, c = np.unravel_index(int(arr.argmax()), arr.shape)
    return (int(c), int(r))  # grid is [row=y][col=x]


def _cheb(a, b) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _plateau_size(grid) -> int:
    """How many cells tie for the maximum. >1 means the argmax is an arbitrary tie-break.

    Under the clamped wire law the field saturates to a flat 0.9 blanket, so this grows to
    40+ of 49 cells and 'follow the scent peak' stops being a defined instruction at all.
    """
    arr = np.array(grid, dtype=float)
    if arr.size == 0 or float(arr.max()) <= 0.0:
        return 0
    return int((arr >= float(arr.max()) - 1e-9).sum())


def summarise(rows: list[dict]) -> dict:
    def avg(key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return round(float(np.mean(vals)), 3) if vals else None

    return {
        "games": len(rows),
        "scent_follow_rate": avg("scent_follow_rate"),
        "scent_chance_rate": avg("scent_chance_rate"),
        "approach_rate": avg("approach_rate"),
        "oscillation_pct": avg("oscillation_pct"),
        "frozen_tail_pct": avg("frozen_tail_pct"),
        "unique_cells": avg("unique_cells"),
        "action_entropy_bits": avg("action_entropy_bits"),
        "stay_pct": avg("stay_pct"),
        "scent_informative_pct": avg("scent_informative_pct"),
        "avg_plateau_cells": avg("avg_plateau_cells"),
    }
