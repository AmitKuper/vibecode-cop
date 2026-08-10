"""Search primitives: legal moves, BFS distances, territory, static evaluation.

Pure functions split verbatim from pursuit_search.py; behavior is pinned by
tests/test_pursuit_search.py and the arena evidence in docs/RL_HYBRID_EVAL.md.
"""

from __future__ import annotations

from collections import deque

from cop_worker.rl.action_space import MOVE_DELTAS

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
            if 0 <= nxt[0] < n and 0 <= nxt[1] < n and nxt not in barriers and nxt not in seen:
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
            if 0 <= nxt[0] < n and 0 <= nxt[1] < n and nxt not in barriers and nxt not in dist:
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
