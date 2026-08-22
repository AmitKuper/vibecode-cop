"""Depth-limited minimax over the KNOWN pursuit state (chebyshev makes both sides sighted).

One search serves both roles: values are cop-positive; the cop maximises, the thief
minimises. A round is thief-move then cop-move-or-place (reference-v3 order). Capture =
co-location after either half-move, a barrier placed on the thief's cell (rule 46), or a
thief with no legal move at its turn (rule 47 — STAY does not rescue). Evaluation blends
BFS pursuit distance with the thief's reachable-region size — the cops-and-robbers
region-shrinking heuristic that makes a barrier worth its forfeited move.
"""

from __future__ import annotations

from cop_worker.rl.pursuit_eval import (  # noqa: F401  (public re-exports)
    CAPTURE,
    SURVIVAL,
    _bfs_distance,
    _dist_map,
    _legal_moves,
    _territory,
    evaluate,
)


def _round_value(
    cop, thief, barriers, barriers_left, steps_left, depth, n, alpha, beta, reorder=False,
    grad=False,
) -> tuple[float, str]:
    """Value of a round boundary (thief to move, cop replies). Returns (value, thief action).

    ``reorder=True`` (interior calls only) explores promising thief moves first for
    earlier alpha-beta cutoffs. The thief ROOT keeps the original order so its
    action tie-breaking is bit-identical; interior callers consume only the VALUE,
    which alpha-beta returns exactly under any child order (root children run full
    windows). Pinned by the golden corpus.

    ``grad=True`` (COP drivers only — the thief's search stays byte-identical at
    the default): clock-exhausted leaves return SURVIVAL plus a tiny static-eval
    gradient instead of one flat constant. Without it, every line past the clock
    ties at SURVIVAL, the root argmax degrades to first-legal-move order, and the
    cop turns AWAY from a fleeing thief (counted g02 vs an evader peer,
    2026-08-22, step 32: chase at BFS 2 with 3 steps left chose N — observed in
    three live series). The gradient also prices mid-chase walls: a wall ahead of
    the flight path cuts territory even when capture is beyond the horizon.
    """
    thief_moves = _legal_moves(thief, barriers, n)
    # Rule 47: STAY does not rescue — enclosed means no NON-STAY move. (_legal_moves
    # always contains STAY, so `not thief_moves` never fired; found live 2026-08-10:
    # the cop had a forced fork — place onto the last exit = rule 47 if the thief
    # stays, rule 46 if it flees into the placement — and could not see it.)
    if not any(a != "STAY" for a, _pos in thief_moves):
        return CAPTURE + steps_left, "STAY"
    if steps_left <= 0:
        if grad:
            return SURVIVAL + 1e-3 * evaluate(cop, thief, barriers, n, 0), "STAY"
        return SURVIVAL, "STAY"
    if reorder and len(thief_moves) > 1:
        from cop_worker.rl.pursuit_cache import evaluate_cached

        thief_moves.sort(key=lambda ap: evaluate_cached(cop, ap[1], barriers, n, steps_left))
    best_value, best_action = float("inf"), thief_moves[0][0]
    for t_action, t_pos in thief_moves:
        if t_pos == cop:
            value = CAPTURE + steps_left  # walked onto the cop: co-location
        else:
            value = _cop_reply(
                cop, t_pos, barriers, barriers_left, steps_left, depth, n, alpha, beta,
                grad=grad,
            )
        if value < best_value:
            best_value, best_action = value, t_action
        beta = min(beta, best_value)
        if beta <= alpha:
            break
    return best_value, best_action


from cop_worker.rl.pursuit_cop import _cop_reply, _cop_root  # noqa: E402,F401


def best_cop_action(
    cop, thief, barriers, barriers_left, steps_left, depth=4, n=7, time_budget_s: float = 10.0
) -> str:
    """The cop's half-move, chosen AFTER the thief has moved this round.

    Iterative deepening under a hard wall-clock budget: raw depth-4 measured up to
    ~74s in open midgame, far too close to a live 180s turn budget. Depths run
    2→``depth``; the deepest COMPLETED depth's action is returned, so latency is
    bounded by ~2x the budget while endgames still search deep (they are cheap).
    Immediate captures (step onto the thief, place onto its cell) short-circuit.
    """
    import time as _time

    from cop_worker.rl import pursuit_cache

    pursuit_cache.reset()  # fresh per root: bounded memory, no staleness
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


def best_thief_action(
    cop,
    thief,
    barriers,
    steps_left,
    depth=4,
    n=7,
    cop_barriers_left=14,
    time_budget_s: float = 10.0,
) -> str:
    """The thief's half-move at the top of a round (thief first; the cop replies).

    Models the cop's remaining wall budget — under-counting it hides enclosure
    danger. Same iterative-deepening latency bound as the cop root.
    """
    import time as _time

    from cop_worker.rl import pursuit_cache

    pursuit_cache.reset()  # fresh per root: bounded memory, no staleness
    barriers = set(map(tuple, barriers))
    deadline = _time.monotonic() + max(0.5, time_budget_s)
    action = "STAY"
    for d in range(2, max(2, depth) + 1):
        t0 = _time.monotonic()
        _value, action = _round_value(
            tuple(cop),
            tuple(thief),
            barriers,
            cop_barriers_left,
            steps_left,
            d,
            n,
            float("-inf"),
            float("inf"),
        )
        elapsed = _time.monotonic() - t0
        if _time.monotonic() + 10.0 * elapsed >= deadline:
            break
    return action
