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


def _dist_map(src, barriers, n) -> dict:
    dist, q = {src: 0}, deque([src])
    while q:
        cell = q.popleft()
        d = dist[cell]
        for dx, dy in _ORTHO:
            nxt = (cell[0] + dx, cell[1] + dy)
            if (0 <= nxt[0] < n and 0 <= nxt[1] < n
                    and nxt not in barriers and nxt not in dist):
                dist[nxt] = d + 1
                q.append(nxt)
    return dist


def _territory(cop, thief, barriers, n) -> int:
    """Cells the thief can reach strictly before the cop — its true escape room.

    This is the pursuit-correct region: a plain flood-fill barely changes when the
    cop approaches, so a horizon-limited minimax saw every approach as futile against
    an optimal dodger and CAMPED (observed live, 2026-08-10 rehearsal: cop parked at
    (4,4) for 20 turns while the thief sat in a corner). Territory strictly shrinks
    as the cop closes and only credits walls that actually cut escape routes.
    """
    td = _dist_map(thief, barriers, n)
    cd = _dist_map(cop, barriers, n)
    return sum(1 for cell, d in td.items() if d < cd.get(cell, 10_000))


def evaluate(cop, thief, barriers, n, steps_left) -> float:
    """Cop-positive static value of a non-terminal round boundary.

    Weights are a measured balance: with distance dominating (60/8) the minimising
    thief PREFERRED a far corner over the open centre (dist 6, territory ~10 beat
    dist 3, territory ~24) and ran itself into the greedy cop's perimeter sweep —
    captured in 11 moves, live, 2026-08-10. At 40/16 the centre-with-escape-room
    wins for the thief, while the cop still has strict approach AND herding
    gradients (both terms improve as it closes or cuts territory).
    """
    dist = _bfs_distance(cop, thief, barriers, n)
    territory = _territory(cop, thief, barriers, n)
    return -40.0 * dist - 16.0 * territory + 2.0 * (35 - steps_left)


def _round_value(cop, thief, barriers, barriers_left, steps_left, depth,
                 n, alpha, beta) -> tuple[float, str]:
    """Value of a round boundary (thief to move, cop replies). Returns (value, thief action)."""
    thief_moves = _legal_moves(thief, barriers, n)
    # Rule 47: STAY does not rescue — enclosed means no NON-STAY move. (_legal_moves
    # always contains STAY, so `not thief_moves` never fired; found live 2026-08-10:
    # the cop had a forced fork — place onto the last exit = rule 47 if the thief
    # stays, rule 46 if it flees into the placement — and could not see it.)
    if not any(a != "STAY" for a, _pos in thief_moves):
        return CAPTURE + steps_left, "STAY"
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


def _cop_root(cop, thief, barriers, barriers_left, steps_left, depth, n) -> str:
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


def best_cop_action(cop, thief, barriers, barriers_left, steps_left,
                    depth=4, n=7, time_budget_s: float = 10.0) -> str:
    """The cop's half-move, chosen AFTER the thief has moved this round.

    Iterative deepening under a hard wall-clock budget: raw depth-4 measured up to
    ~74s in open midgame, far too close to a live 180s turn budget. Depths run
    2→``depth``; the deepest COMPLETED depth's action is returned, so latency is
    bounded by ~2x the budget while endgames still search deep (they are cheap).
    Immediate captures (step onto the thief, place onto its cell) short-circuit.
    """
    import time as _time

    barriers = set(map(tuple, barriers))
    cop, thief = tuple(cop), tuple(thief)
    deadline = _time.monotonic() + max(0.5, time_budget_s)
    action = "STAY"
    for d in range(2, max(2, depth) + 1):
        t0 = _time.monotonic()
        action = _cop_root(cop, thief, barriers, barriers_left, steps_left, d, n)
        elapsed = _time.monotonic() - t0
        # Don't START a depth we cannot afford: one ply multiplies cost ~10x
        # (measured d3→d4: 7.8s→67s), and a between-depths check alone let a
        # 74s depth-4 through the "10s" budget.
        if _time.monotonic() + 10.0 * elapsed >= deadline:
            break
    return action


def best_thief_action(cop, thief, barriers, steps_left, depth=4, n=7,
                      cop_barriers_left=14, time_budget_s: float = 10.0) -> str:
    """The thief's half-move at the top of a round (thief first; the cop replies).

    Models the cop's remaining wall budget — under-counting it hides enclosure
    danger. Same iterative-deepening latency bound as the cop root.
    """
    import time as _time

    barriers = set(map(tuple, barriers))
    deadline = _time.monotonic() + max(0.5, time_budget_s)
    action = "STAY"
    for d in range(2, max(2, depth) + 1):
        t0 = _time.monotonic()
        _value, action = _round_value(tuple(cop), tuple(thief), barriers,
                                      cop_barriers_left, steps_left, d, n,
                                      float("-inf"), float("inf"))
        elapsed = _time.monotonic() - t0
        if _time.monotonic() + 10.0 * elapsed >= deadline:
            break
    return action
