"""Cop-side minimax drivers: reply search and root action selection.

Split verbatim from pursuit_search.py; behavior pinned by tests.
"""

from __future__ import annotations

from cop_worker.rl.action_space import PLACE_DIRS
from cop_worker.rl.pursuit_eval import CAPTURE, _legal_moves, evaluate
from cop_worker.rl.pursuit_search import _round_value


def _cop_reply(cop, thief, barriers, barriers_left, steps_left, depth, n, alpha, beta) -> float:
    def _descend(c_pos, walls, b_left) -> float:
        if depth <= 1:
            return evaluate(c_pos, thief, walls, n, steps_left - 1)
        value, _ = _round_value(
            c_pos, thief, walls, b_left, steps_left - 1, depth - 1, n, alpha, beta
        )
        return value

    best = float("-inf")
    for _a, c_pos in _legal_moves(cop, barriers, n):
        if c_pos == thief:
            return CAPTURE + steps_left
        best = max(best, _descend(c_pos, barriers, barriers_left))
        alpha = max(alpha, best)
        if beta <= alpha:
            return best
    if barriers_left > 0:
        for _a, (dx, dy) in PLACE_DIRS.items():
            cell = (cop[0] + dx, cop[1] + dy)
            if not (0 <= cell[0] < n and 0 <= cell[1] < n) or cell in barriers:
                continue
            if cell == thief:
                return CAPTURE + steps_left  # rule 46: wall dropped on the thief
            best = max(best, _descend(cop, barriers | {cell}, barriers_left - 1))
            alpha = max(alpha, best)
            if beta <= alpha:
                return best
    if best == float("-inf"):
        best = evaluate(cop, thief, barriers, n, steps_left - 1)  # cop immobilised
    return best


def _cop_root(cop, thief, barriers, barriers_left, steps_left, depth, n) -> str:
    best_action, best_value = "STAY", float("-inf")
    for action, c_pos in _legal_moves(cop, barriers, n):
        if c_pos == thief:
            return action
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
        if value > best_value:
            best_value, best_action = value, action
    if barriers_left > 0:
        for action, (dx, dy) in PLACE_DIRS.items():
            cell = (cop[0] + dx, cop[1] + dy)
            if not (0 <= cell[0] < n and 0 <= cell[1] < n) or cell in barriers:
                continue
            if cell == thief:
                return action
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
            if value > best_value:
                best_value, best_action = value, action
    return best_action
