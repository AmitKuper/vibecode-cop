"""Adversarial-archetype sweep: opponent styles we have NOT otherwise tested.

WallCutterCop  — area-denial: builds a mid-board wall, then hunts the smaller half.
ParityDodger   — classic anti-chaser thief: max distance + opposite parity.
ClaimForkCop   — greedy chase that places onto the thief the moment it is adjacent.

Run: python scripts/arena_archetypes.py
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for p in (REPO_ROOT, REPO_ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import arena_search_eval as A  # noqa: E402
from cop_worker.rl.action_space import MOVE_DELTAS, PLACE_DIRS  # noqa: E402
from cop_worker.rl.chebyshev_tracker import exact_opponent_cell  # noqa: E402
from cop_worker.rl.search_policy import SearchRolePolicy  # noqa: E402

N = 7


class WallCutterCop:
    """Build a wall on column 3, then greedy-chase the frame peak in the cut board."""

    def __init__(self) -> None:
        self.rng = random.Random(7)

    def reset(self) -> None:
        pass

    def select_action(self, obs, belief, legal):
        x, y = obs.own_position
        walls = set(map(tuple, obs.known_barriers))
        if obs.own_barriers_remaining > 8:
            for wy in range(N):
                if (3, wy) in walls:
                    continue
                if (x, y) == (2, wy) and "PLACE_E" in legal:
                    return "PLACE_E"
                if (x, y) == (4, wy) and "PLACE_W" in legal:
                    return "PLACE_W"
                for a, want in (("E", x < 2), ("W", x > 2), ("S", y < wy), ("N", y > wy)):
                    if want and a in legal:
                        return a
                break
            return "STAY" if "STAY" in legal else legal[0]
        opp = exact_opponent_cell(obs.opponent_scent, N)
        if opp:
            tx, ty = opp
            for a, want in (("E", x < tx), ("W", x > tx), ("S", y < ty), ("N", y > ty)):
                if want and a in legal:
                    return a
        return self.rng.choice(legal)


class ParityDodger:
    """Maximise distance, prefer opposite parity (unreachable by a bare chaser)."""

    def reset(self) -> None:
        pass

    def select_action(self, obs, belief, legal):
        x, y = obs.own_position
        cop = exact_opponent_cell(obs.opponent_scent, N)
        if cop is None:
            return "STAY" if "STAY" in legal else legal[0]
        best, best_score = legal[0], float("-inf")
        for a in legal:
            dx, dy = MOVE_DELTAS.get(a, (0, 0))
            nx, ny = x + dx, y + dy
            dist = abs(nx - cop[0]) + abs(ny - cop[1])
            parity = (nx + ny + cop[0] + cop[1]) % 2
            centrality = -(abs(nx - 3) + abs(ny - 3)) * 0.3
            score = 2.0 * dist + 3.0 * parity + centrality
            if score > best_score:
                best, best_score = a, score
        return best


class ClaimForkCop:
    """Greedy chase; the moment the thief is orthogonally adjacent, PLACE onto it."""

    def reset(self) -> None:
        pass

    def select_action(self, obs, belief, legal):
        x, y = obs.own_position
        opp = exact_opponent_cell(obs.opponent_scent, N)
        if opp is None:
            return "STAY" if "STAY" in legal else legal[0]
        tx, ty = opp
        for a, (dx, dy) in PLACE_DIRS.items():
            if (x + dx, y + dy) == (tx, ty) and a in legal:
                return a
        if abs(x - tx) >= abs(y - ty):
            prefs = (["E"] if x < tx else ["W"]) + (["S"] if y < ty else ["N"])
        else:
            prefs = (["S"] if y < ty else ["N"]) + (["E"] if x < tx else ["W"])
        for a in prefs:
            if a in legal:
                return a
        return "STAY" if "STAY" in legal else legal[0]


def run(name, cop, thief, games=6):
    caps, steps = 0, []
    for g in range(games):
        outcome, step = A.play(cop, thief, 20260810 + g, True)
        caps += outcome == "capture"
        steps.append(step)
    print(f"{name}: captures {caps}/{games}, end steps {steps}")


if __name__ == "__main__":
    t0 = time.time()
    run("WallCutter cop   vs OUR thief    ", WallCutterCop(), SearchRolePolicy("thief", depth=4))
    run("ClaimFork cop    vs OUR thief    ", ClaimForkCop(), SearchRolePolicy("thief", depth=4))
    run("OUR cop          vs ParityDodger ", SearchRolePolicy("cop", depth=4), ParityDodger())
    print(f"wall {time.time() - t0:.0f}s")
