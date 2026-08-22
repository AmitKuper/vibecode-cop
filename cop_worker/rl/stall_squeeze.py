"""Stall-squeeze: barrier override for the cop against optimal evaders.

Measured 2026-08-20 (post-SMNGRP05 47-47): without barriers a 7x7 pursuit is
thief-win from EVERY start under optimal play (exact backward induction), so
a cop that never walls can never beat an exact-evader thief — it stalls at
distance 2 forever. This hook detects that stall and places the adjacent
barrier that most shrinks the thief's exactly-solved surviving-move set; the
evader's own table then turns against it (lab: capture in 10-21 steps vs
re-solving evaders that survived all 35 against plain minimax).

Fires only after ``STALL_TURNS`` consecutive stable-distance close-range
turns — states where minimax provably oscillates without capture — so it
cannot interfere with a converging chase. Never walls the cop's own last
exit, never places without strict metric improvement, never places a wall
that lengthens the cop's own BFS path to the thief (counted g02 vs an
evader, 2026-08-22: the hook's walls formed a chain that left the thief's
pocket reachable only via a 16-step detour with 12 steps on the clock —
the squeeze sealed the cop OUT, not the thief in), and stops after
``MAX_HOOK_WALLS`` placements.
"""

from __future__ import annotations

from cop_worker.rl.action_space import PLACE_DIRS
from cop_worker.rl.pursuit_eval import _bfs_distance

ORTHO = ((-1, 0), (1, 0), (0, -1), (0, 1))
# Delta -> action name in the PRODUCTION convention (action_space / domain
# transition / minimax all agree PLACE_N == (0, -1)). Derived, not hand-typed:
# a hand-typed copy once rotated every hook wall 90 degrees on the wire.
_PLACE = {tuple(delta): name for name, delta in PLACE_DIRS.items()}
STALL_TURNS = 4
MAX_HOOK_WALLS = 8
_MAX_LAYERS = 35


def survival_layers(walls: frozenset, n: int, steps: int = _MAX_LAYERS):
    """Exact thief-survival tables on the CURRENT walls (thief moves first,
    STAY allowed, capture on co-location, rule-47 immobilization)."""
    cells = [(r, c) for r in range(n) for c in range(n) if (r, c) not in walls]
    idx = {p: i for i, p in enumerate(cells)}
    neigh = []
    for p in cells:
        opts = [idx[p]]
        for dr, dc in ORTHO:
            q = (p[0] + dr, p[1] + dc)
            if 0 <= q[0] < n and 0 <= q[1] < n and q not in walls:
                opts.append(idx[q])
        neigh.append(opts)
    m = len(cells)
    prev = [[True] * m for _ in range(m)]
    layers = [prev]
    for _ in range(steps):
        cur = [[False] * m for _ in range(m)]
        for c in range(m):
            row = cur[c]
            for t in range(m):
                if c == t:
                    continue
                for t2 in neigh[t]:
                    if t2 == c:
                        continue
                    for c2 in neigh[c]:
                        if c2 == t2 or not prev[c2][t2]:
                            break
                    else:
                        row[t] = True
                        break
        layers.append(cur)
        prev = cur
    return layers, idx


class StallSqueeze:
    """Per-sub-game stall detector + barrier chooser (cop only)."""

    def __init__(self, n: int = 7) -> None:
        self.n = n
        self._cache: dict[frozenset, tuple] = {}
        self.reset()

    def reset(self) -> None:
        self._stall = 0
        self._last_d = None
        self._hook_walls = 0

    def _surviving_moves(self, cop, thief, walls, steps_left) -> int:
        if walls not in self._cache:
            if len(self._cache) >= 16:  # bound memory across sub-games
                self._cache.clear()
            self._cache[walls] = survival_layers(walls, self.n)
        layers, idx = self._cache[walls]
        s = max(0, min(steps_left - 1, _MAX_LAYERS))
        cnt = 0
        for dr, dc in ORTHO + ((0, 0),):
            q = (thief[0] + dr, thief[1] + dc)
            if (
                not (0 <= q[0] < self.n and 0 <= q[1] < self.n)
                or q in walls
                or q == cop
                or q not in idx
            ):
                continue
            if layers[s][idx[cop]][idx[q]]:
                cnt += 1
        return cnt

    def override(
        self, cop, thief, barriers, barriers_left, steps_left, legal_actions
    ) -> str | None:
        """Update stall state; return a PLACE_* action or None (keep minimax)."""
        d = abs(cop[0] - thief[0]) + abs(cop[1] - thief[1])
        stable = self._last_d is not None and abs(d - self._last_d) <= 1 and d <= 4
        self._stall = self._stall + 1 if stable else 0
        self._last_d = d
        # d <= 1 is capture-in-hand: minimax takes the thief this half-move
        # (step onto it, or rule-46 place onto its cell) — never preempt that.
        if (
            d <= 1
            or self._stall < STALL_TURNS
            or barriers_left <= 0
            or self._hook_walls >= MAX_HOOK_WALLS
        ):
            return None
        walls = frozenset(map(tuple, barriers))
        base = self._surviving_moves(cop, thief, walls, steps_left)
        base_bfs = _bfs_distance(tuple(cop), tuple(thief), walls, self.n)
        best_action, best_score = None, base
        for (dr, dc), name in _PLACE.items():
            cell = (cop[0] + dr, cop[1] + dc)
            if (
                not (0 <= cell[0] < self.n and 0 <= cell[1] < self.n)
                or cell in walls
                or cell == thief
                or name not in legal_actions
            ):
                continue
            # Self-cutoff guard: the squeeze's between-cell wall legitimately
            # re-routes the cop by +2 (around one cell); anything worse is
            # sealing the cop OUT of the thief's region, not squeezing it.
            if _bfs_distance(tuple(cop), tuple(thief), walls | {cell}, self.n) > base_bfs + 2:
                continue
            exits = sum(
                1
                for dr2, dc2 in ORTHO
                if 0 <= cop[0] + dr2 < self.n
                and 0 <= cop[1] + dc2 < self.n
                and (cop[0] + dr2, cop[1] + dc2) not in walls | {cell}
            )
            if exits < 2:
                continue
            score = self._surviving_moves(cop, thief, walls | {cell}, steps_left)
            if score < best_score:
                best_score, best_action = score, name
        if best_action is not None:
            self._stall = 0
            self._hook_walls += 1
        return best_action
