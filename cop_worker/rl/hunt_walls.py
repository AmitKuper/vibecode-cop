"""Cut-reducing wall chooser for the committed hunt (split, 150-line rule)."""

from __future__ import annotations

from cop_worker.rl.sealability import ORTHO, sealability
from cop_worker.rl.stall_squeeze import _PLACE

CUT_MAX = 4


def best_cut_wall(cop, thief, prev, walls, legal_actions, n) -> str | None:
    """The PLACE_* action that most reduces a dance-target's escape cut.

    Targets the thief's current cell and (when distinct) its previous cell —
    the two ends of the oscillation. Never walls the cop's own last exits.
    Returns None when no candidate strictly reduces a cut <= CUT_MAX.
    """
    targets = {thief: sealability(thief, cop, walls, n)}
    if prev is not None and prev != thief and prev not in walls:
        targets[prev] = sealability(prev, cop, walls, n)
    if min(targets.values()) > CUT_MAX:
        return None
    best_action, best_key = None, None
    for (dx, dy), name in _PLACE.items():
        if name not in legal_actions:
            continue
        cell = (cop[0] + dx, cop[1] + dy)
        if not (0 <= cell[0] < n and 0 <= cell[1] < n) or cell in walls or cell == thief:
            continue
        exits = sum(
            1
            for dx2, dy2 in ORTHO
            if 0 <= cop[0] + dx2 < n
            and 0 <= cop[1] + dy2 < n
            and (cop[0] + dx2, cop[1] + dy2) not in walls | {cell}
        )
        if exits < 2:  # never wall our own last exits
            continue
        gain = None
        for t, c0 in targets.items():
            if cell == t:
                continue
            nc = sealability(t, cop, walls | {cell}, n)
            if nc < c0 and (gain is None or nc < gain):
                gain = nc
        if gain is None:
            continue
        key = (gain, abs(cell[0] - thief[0]) + abs(cell[1] - thief[1]))
        if best_key is None or key < best_key:
            best_key, best_action = key, name
    return best_action
