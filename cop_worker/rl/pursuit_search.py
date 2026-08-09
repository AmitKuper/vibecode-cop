"""Depth-limited minimax over the KNOWN pursuit state (chebyshev makes both sides sighted).

One search serves both roles: values are cop-positive; the cop maximises, the thief
minimises. A round is thief-move then cop-move-or-place (reference-v3 order). Capture =
co-location after either half-move, a barrier placed on the thief's cell (rule 46), or a
thief with no legal move at its turn (rule 47 — STAY does not rescue). Evaluation blends
BFS pursuit distance with the thief's reachable-region size — the cops-and-robbers
region-shrinking heuristic that makes a barrier worth its forfeited move.
"""

from __future__ import annotations

from collections import deque

from cop_worker.rl.action_space import MOVE_DELTAS, PLACE_DIRS

CAPTURE = 10_000.0
SURVIVAL = -10_000.0
_ORTHO = ((0, -1), (0, 1), (1, 0), (-1, 0))


def _legal_moves(pos, barriers, n):
    out = []
    for a, (dx, dy) in MOVE_DELTAS.items():
        nx, ny = pos[0] + dx, pos[1] + dy
        if 0 <= nx < n and 0 <= ny < n and (nx, ny) not in barriers:
            out.append((a, (nx, ny)))
    return out


def _bfs_distance(src, dst, barriers, n) -> int:
    if src == dst:
        return 0
    seen, q = {src}, deque([(src, 0)])
    while q:
        (x, y), d = q.popleft()
        for dx, dy in _ORTHO:
            nxt = (x + dx, y + dy)
            if nxt == dst:
                return d + 1
            if (0 <= nxt[0] < n and 0 <= nxt[1] < n
                    and nxt not in barriers and nxt not in seen):
                seen.add(nxt)
                q.append((nxt, d + 1))
    return 2 * n * n  # walled off from each other


def _region_size(pos, barriers, n) -> int:
    seen, q = {pos}, deque([pos])
    while q:
        x, y = q.popleft()
        for dx, dy in _ORTHO:
            nxt = (x + dx, y + dy)
            if (0 <= nxt[0] < n and 0 <= nxt[1] < n
                    and nxt not in barriers and nxt not in seen):
                seen.add(nxt)
                q.append(nxt)
    return len(seen)


def evaluate(cop, thief, barriers, n, steps_left) -> float:
    """Cop-positive static value of a non-terminal round boundary."""
    dist = _bfs_distance(cop, thief, barriers, n)
    region = _region_size(thief, barriers, n)
    # Pursuit pressure dominates; shrinking the thief's world is the long game; the
    # clock favours the thief, so time already spent counts FOR the cop only weakly.
    return -60.0 * dist - 8.0 * region + 2.0 * (35 - steps_left)


def _round_value(cop, thief, barriers, barriers_left, steps_left, depth,
                 n, alpha, beta) -> tuple[float, str]:
    """Value of a round boundary (thief to move, cop replies). Returns (value, thief action)."""
    thief_moves = _legal_moves(thief, barriers, n)
    if not thief_moves:
        return CAPTURE + steps_left, "STAY"  # rule 47: enclosed at its turn
    if steps_left <= 0:
        return SURVIVAL, "STAY"
    best_value, best_action = float("inf"), thief_moves[0][0]
    for t_action, t_pos in thief_moves:
        if t_pos == cop:
            value = CAPTURE + steps_left  # walked onto the cop: co-location
        else:
            value = _cop_reply(cop, t_pos, barriers, barriers_left,
                               steps_left, depth, n, alpha, beta)
        if value < best_value:
            best_value, best_action = value, t_action
        beta = min(beta, best_value)
        if beta <= alpha:
            break
    return best_value, best_action


def _cop_reply(cop, thief, barriers, barriers_left, steps_left, depth,
               n, alpha, beta) -> float:
    def _descend(c_pos, walls, b_left) -> float:
        if depth <= 1:
            return evaluate(c_pos, thief, walls, n, steps_left - 1)
        value, _ = _round_value(c_pos, thief, walls, b_left, steps_left - 1,
                                depth - 1, n, alpha, beta)
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


def best_cop_action(cop, thief, barriers, barriers_left, steps_left,
                    depth=3, n=7) -> str:
    """The cop's half-move, chosen AFTER the thief has moved this round.

    Immediate captures (step onto the thief, or place onto its cell) short-circuit.
    """
    barriers = set(map(tuple, barriers))
    cop, thief = tuple(cop), tuple(thief)
    best_action, best_value = "STAY", float("-inf")
    for action, c_pos in _legal_moves(cop, barriers, n):
        if c_pos == thief:
            return action
        value, _ = _round_value(c_pos, thief, barriers, barriers_left,
                                steps_left - 1, depth, n,
                                float("-inf"), float("inf"))
        if value > best_value:
            best_value, best_action = value, action
    if barriers_left > 0:
        for action, (dx, dy) in PLACE_DIRS.items():
            cell = (cop[0] + dx, cop[1] + dy)
            if not (0 <= cell[0] < n and 0 <= cell[1] < n) or cell in barriers:
                continue
            if cell == thief:
                return action
            value, _ = _round_value(cop, thief, barriers | {cell}, barriers_left - 1,
                                    steps_left - 1, depth, n,
                                    float("-inf"), float("inf"))
            if value > best_value:
                best_value, best_action = value, action
    return best_action


def best_thief_action(cop, thief, barriers, steps_left, depth=3, n=7,
                      cop_barriers_left=14) -> str:
    """The thief's half-move at the top of a round (thief first; the cop replies).

    Models the cop's remaining wall budget — under-counting it hides enclosure danger.
    """
    barriers = set(map(tuple, barriers))
    _value, action = _round_value(tuple(cop), tuple(thief), barriers,
                                  cop_barriers_left, steps_left, depth, n,
                                  float("-inf"), float("inf"))
    return action
