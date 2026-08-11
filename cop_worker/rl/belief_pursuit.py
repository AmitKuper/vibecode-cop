"""Belief-state pursuit search: the sighted minimax generalized to a posterior.

Under the book scent law there is no position oracle, but serving now carries a
live Bayesian posterior. This module runs the EXISTING depth-limited pursuit
search once per high-mass belief cell ("particle") and aggregates each cop
action's value weighted by particle probability (QMDP-style determinization).
Barrier placements compete with moves in the same value units, so enclosure is
chosen whenever one wall shrinks the escape room of MANY likely cells at once.

Pure addition: nothing imports this module until a profile opts in via the
``hybrid_search_belief`` move policy. The exact-position engine
(:mod:`cop_worker.rl.pursuit_search`) is reused untouched.
"""

from __future__ import annotations

import time as _time

import numpy as np

from cop_worker.rl.action_space import PLACE_DIRS
from cop_worker.rl.pursuit_eval import CAPTURE, _legal_moves
from cop_worker.rl.pursuit_search import _round_value

#: Ignore particles carrying less than this fraction of the retained mass.
MIN_PARTICLE_WEIGHT = 0.02


def top_particles(prob, k: int = 6, n: int = 7) -> list[tuple[tuple[int, int], float]]:
    """The ``k`` most probable opponent cells as ((x, y), renormalized weight)."""
    grid = np.asarray(prob, dtype=float).reshape(n, n)
    flat = grid.ravel()
    order = np.argsort(flat)[::-1][: max(1, k)]
    picked = [(int(i % n), int(i // n), float(flat[i])) for i in order if flat[i] > 0.0]
    total = sum(w for _x, _y, w in picked) or 1.0
    kept = [((x, y), w / total) for x, y, w in picked if w / total >= MIN_PARTICLE_WEIGHT]
    return kept or [((int(order[0] % n), int(order[0] // n)), 1.0)]


def belief_peak(prob) -> float:
    """The posterior's maximum cell mass — the serving-side confidence gate."""
    return float(np.asarray(prob, dtype=float).max())


def _cop_action_values(
    cop, thief, barriers, barriers_left, steps_left, depth, n
) -> dict[str, float]:
    """Every legal cop action's cop-positive value against ONE assumed thief cell.

    Mirrors :func:`cop_worker.rl.pursuit_cop._cop_root` (kept untouched) but
    returns the full map instead of the argmax, so values can be aggregated
    across belief particles. Immediate captures score as terminal captures.
    """
    values: dict[str, float] = {}
    for action, c_pos in _legal_moves(cop, barriers, n):
        if c_pos == thief:
            values[action] = CAPTURE + steps_left
            continue
        value, _ = _round_value(
            c_pos,
            thief,
            barriers,
            barriers_left,
            steps_left - 1,
            depth,
            n,
            float("-inf"),
            float("inf"),
        )
        values[action] = value
    if barriers_left > 0:
        for action, (dx, dy) in PLACE_DIRS.items():
            cell = (cop[0] + dx, cop[1] + dy)
            if not (0 <= cell[0] < n and 0 <= cell[1] < n) or cell in barriers:
                continue
            if cell == thief:
                values[action] = CAPTURE + steps_left  # rule 46
                continue
            value, _ = _round_value(
                cop,
                thief,
                barriers | {cell},
                barriers_left - 1,
                steps_left - 1,
                depth,
                n,
                float("-inf"),
                float("inf"),
            )
            values[action] = value
    return values


def belief_cop_action_values(
    cop, prob, barriers, barriers_left, steps_left, depth, n=7, k_particles=6
) -> dict[str, float]:
    """Probability-weighted action values across the top belief particles."""
    barriers = set(map(tuple, barriers))
    cop = tuple(cop)
    aggregate: dict[str, float] = {}
    for cell, weight in top_particles(prob, k_particles, n):
        if cell == cop or cell in barriers:
            continue  # the opponent cannot be under us or inside a wall
        for action, value in _cop_action_values(
            cop, cell, barriers, barriers_left, steps_left, depth, n
        ).items():
            aggregate[action] = aggregate.get(action, 0.0) + weight * value
    return aggregate


def belief_best_cop_action(
    cop,
    prob,
    barriers,
    barriers_left,
    steps_left,
    depth: int = 3,
    n: int = 7,
    k_particles: int = 6,
    time_budget_s: float = 10.0,
) -> str:
    """The cop's half-move under positional uncertainty.

    Iterative deepening under the same hard wall-clock discipline as the exact
    engine: depths run 2→``depth``; a new depth only STARTS if the projected
    cost (measured last-depth cost x10, the measured per-ply blowup) fits the
    budget. The deepest completed depth's argmax is returned; ties break toward
    non-STAY so a flat aggregate still applies pressure.
    """
    deadline = _time.monotonic() + max(0.5, time_budget_s)
    best = "STAY"
    for d in range(2, max(2, depth) + 1):
        t0 = _time.monotonic()
        values = belief_cop_action_values(
            cop, prob, barriers, barriers_left, steps_left, d, n, k_particles
        )
        if values:
            best = max(values.items(), key=lambda kv: (kv[1], kv[0] != "STAY"))[0]
        elapsed = _time.monotonic() - t0
        if _time.monotonic() + 10.0 * elapsed >= deadline:
            break
    return best
