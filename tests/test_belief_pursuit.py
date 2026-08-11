"""belief_pursuit — particle aggregation, exact-engine agreement, enclosure value."""

from __future__ import annotations

import numpy as np

from cop_worker.rl.belief_pursuit import (
    belief_best_cop_action,
    belief_cop_action_values,
    belief_peak,
    top_particles,
)
from cop_worker.rl.pursuit_search import best_cop_action

N = 7


def _prob_at(cells_weights):
    grid = np.zeros((N, N))
    for (x, y), w in cells_weights:
        grid[y, x] = w
    return grid / grid.sum()


def test_top_particles_orders_and_renormalizes():
    prob = _prob_at([((5, 5), 0.7), ((1, 1), 0.2), ((3, 0), 0.1)])
    particles = top_particles(prob, k=2)
    assert particles[0][0] == (5, 5) and particles[1][0] == (1, 1)
    assert abs(sum(w for _c, w in particles) - 1.0) < 1e-9
    assert belief_peak(prob) > 0.6


def test_concentrated_belief_matches_the_exact_engine():
    prob = _prob_at([((5, 5), 1.0)])
    for cop in [(0, 0), (3, 3), (5, 3)]:
        got = belief_best_cop_action(cop, prob, [], 14, 20, depth=2, time_budget_s=2.0)
        exact = best_cop_action(cop, (5, 5), [], 14, 20, depth=2, time_budget_s=2.0)
        assert got == exact, f"cop {cop}: belief {got} != exact {exact}"


def test_immediate_capture_is_taken():
    prob = _prob_at([((3, 2), 1.0)])
    action = belief_best_cop_action((3, 3), prob, [], 14, 20, depth=2, time_budget_s=1.0)
    assert action in ("N", "PLACE_N")  # step onto or wall onto the certain cell


def test_walling_a_shared_exit_beats_chasing():
    # Thief is certainly in the top-right pocket (two likely cells) whose only
    # exit is (5, 1); the cop stands beside the gap. Sealing it must outscore
    # any step for the aggregate across BOTH cells.
    barriers = [(4, 0), (4, 1), (4, 2), (5, 2), (6, 2)]
    prob = _prob_at([((6, 0), 0.6), ((6, 1), 0.4)])
    values = belief_cop_action_values((5, 1), prob, barriers, 5, 24, depth=2)
    wall = (
        values["PLACE_E"]
        if "PLACE_E" in values
        else max(v for a, v in values.items() if a.startswith("PLACE_"))
    )
    best_move = max(v for a, v in values.items() if not a.startswith("PLACE_"))
    assert wall > best_move


def test_flat_belief_still_returns_a_legal_action():
    prob = np.full((N, N), 1.0 / (N * N))
    action = belief_best_cop_action((0, 0), prob, [], 14, 35, depth=2, time_budget_s=1.0)
    assert action in {"N", "S", "E", "W", "STAY", "PLACE_N", "PLACE_S", "PLACE_E", "PLACE_W"}


def test_particles_on_our_cell_or_walls_are_skipped():
    prob = _prob_at([((2, 2), 0.5), ((4, 4), 0.5)])
    values = belief_cop_action_values((2, 2), prob, [(4, 4)], 14, 20, depth=2)
    # both particles are excluded (our cell + a wall) -> empty aggregate
    assert values == {}
