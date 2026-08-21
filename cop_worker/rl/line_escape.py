"""Confined-mode thief: exact survival play against partition-building cops.

Measured 2026-08-21 (yanell11 friendly, records g03/g05): a cop that builds
a wall LINE with one door, crosses, and pockets the thief captures our
depth-4 minimax thief at ~step 25 — and depth 6/8 die identically (the
pocket refutation lies beyond any practical horizon). What DOES survive it,
measured in scripts/line_sweep_lab.py, is exact current-walls survival play
with a mobility tie-break — the same class of evader that drew us 47-47 as
an opponent. Mobility bias is what dodges both the sweep and the corner
deaths that killed minimax.

So: when a completable wall line is forming (>= 2 collinear walls within
the cop's remaining budget) OR the thief's escape cut is narrow (pocket
threat, operator-found 2026-08-21), the thief switches to the exact-table
evader with wall-aware tie-breaks: cop-reply-correct survival, wall-safe
(continuations left after the cop's best adjacent placement), sealability
(min-cut to open space), mobility, distance. Verified in pocketer_lab
(adaptive pocketing AND line-hunt: survival), line_sweep_lab and
corridor_lab; with no threat it plays byte-identical minimax.
"""

from __future__ import annotations

from cop_worker.rl.stall_squeeze import survival_layers

ORTHO = ((-1, 0), (1, 0), (0, -1), (0, 1))
_NAMES = {(-1, 0): "W", (1, 0): "E", (0, -1): "N", (0, 1): "S", (0, 0): "STAY"}
MIN_LINE_WALLS = 2


def _threat_line(walls: frozenset, cop_barriers_left: int, n: int) -> bool:
    """True when any interior row/col line is >= 2 built and completable."""
    for axis in (0, 1):
        for k in range(1, n - 1):  # an edge line partitions nothing
            cells = {(k, j) if axis == 0 else (j, k) for j in range(n)}
            built = len(cells & walls)
            if built >= MIN_LINE_WALLS and len(cells - walls) <= cop_barriers_left:
                return True
    return False


class LineEscape:
    """Per-sub-game confined-mode switch for the thief."""

    def __init__(self, n: int = 7) -> None:
        self.n = n
        self._cache: dict[frozenset, tuple] = {}

    def reset(self) -> None:
        self._cache.clear()

    def _table(self, walls: frozenset):
        if walls not in self._cache:
            if len(self._cache) >= 8:  # bound memory across sub-games
                self._cache.clear()
            self._cache[walls] = survival_layers(walls, self.n)
        return self._cache[walls]

    def _mobility(self, q, walls) -> int:
        return sum(
            1
            for dx, dy in ORTHO
            if 0 <= q[0] + dx < self.n
            and 0 <= q[1] + dy < self.n
            and (q[0] + dx, q[1] + dy) not in walls
        )

    def override(
        self, thief, cop, barriers, cop_barriers_left, steps_left, planned: str, legal
    ) -> str | None:
        """Exact-evader move under a line OR pocket threat; None keeps minimax."""
        from cop_worker.rl.sealability import sealability

        walls = frozenset(map(tuple, barriers))
        # Pocket threat (operator-found, 2026-08-21): an adaptive wall-placer
        # needs only ``cut`` future walls to seal us — treat a narrow escape
        # cut like a forming line once the cop has started walling.
        pocket = (
            len(walls) >= 1
            and int(cop_barriers_left) >= (cut := sealability(thief, cop, walls, self.n))
            and cut <= 4  # trigger EARLY and stay on — a flapping trigger lets
            # minimax undo the escape between activations (observed vs the
            # adaptive pocketer: herded to cut 3 during the off-phases)
        )
        if not pocket and not _threat_line(walls, int(cop_barriers_left), self.n):
            return None
        layers, idx = self._table(walls)
        s = max(0, min(steps_left - 1, 35))
        cop_t, thief_t = tuple(cop), tuple(thief)
        if cop_t not in idx or thief_t not in idx:
            return None
        # Turn parity: after WE land on q the COP replies. layers[s][c][t] is
        # "thief to move" — using it directly on q marks cop-adjacent cells
        # survivable (fatal, observed: STAY next to the cop, captured s16).
        # Committing to q survives iff EVERY cop reply c2 misses q and leaves
        # a thief-to-move surviving state.
        cop_replies = [idx[cop_t]]
        for dx, dy in ORTHO:
            c2 = (cop[0] + dx, cop[1] + dy)
            if c2 in idx:
                cop_replies.append(idx[c2])
        s2 = max(0, s - 1)
        options = []
        for (dx, dy), name in _NAMES.items():
            if name not in legal:
                continue
            q = (thief[0] + dx, thief[1] + dy)
            if not (0 <= q[0] < self.n and 0 <= q[1] < self.n) or q in walls or q == cop_t:
                continue
            qi = idx[q]
            surv = 1 if all(c2 != qi and layers[s2][c2][qi] for c2 in cop_replies) else 0
            dist = abs(q[0] - cop[0]) + abs(q[1] - cop[1])
            # Order after survival: WALL-SAFE — continuations left after the
            # cop's best adjacent wall (a cut-1 cell dies to one placement:
            # the operator's corner-seal finish); then sealability; mobility;
            # distance last. Two richer terms were tried here and measurably
            # LOST games — a partition-crossing/door-dance score (thrashes
            # against door-closing line hunters) and a safe-area BFS (breaks
            # the sweep/pocket dances). Do not reintroduce either without
            # rerunning pocketer_lab + line_sweep_lab + corridor_lab.
            wallsafe = self._wall_safe(q, cop_t, walls, layers, idx, s2, cop_barriers_left)
            seal = min(sealability(q, cop_t, walls, self.n), 4)
            options.append((surv, wallsafe, seal, self._mobility(q, walls), min(dist, 3), name))
        if not options:
            return None
        options.sort(reverse=True)
        best = options[0][5]
        return best if best != planned else None

    def _wall_safe(self, q, cop_t, walls, layers, idx, s2, budget) -> int:
        """Surviving continuations from ``q`` after the cop's WORST adjacent
        wall placement (one-ply wall lookahead, capped at 3). The grind
        endgame kills by walling the thief's only continuation; a candidate
        whose escape routes a single placement can erase scores 0 here."""
        conts = [
            m
            for dx, dy in (*ORTHO, (0, 0))
            if (m := (q[0] + dx, q[1] + dy)) in idx
            and m != cop_t
            and layers[s2][idx[cop_t]][idx[m]]
        ]
        if int(budget) <= 0:
            return min(len(conts), 3)
        worst = len(conts)
        for dx, dy in ORTHO:
            p = (cop_t[0] + dx, cop_t[1] + dy)
            if p in idx and p != q:
                worst = min(worst, sum(1 for m in conts if m != p))
        return min(worst, 3)
