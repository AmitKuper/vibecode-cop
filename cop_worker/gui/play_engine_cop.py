"""The model COP's half-move for human-vs-model play (split from play_engine).

Selectable model cop (operator request): "hunt" (default — committed-hunt,
the only cop that captures our own thief class), "corridor" (chain kept for
comparison), or "plain" (squeeze + minimax only — the counted-wire default
chain since 2026-08-23). The plan layer differs; squeeze + minimax are
common to all three.
"""

from __future__ import annotations

from cop_worker.rl.action_space import PLACE_DIRS
from cop_worker.rl.pursuit_search import best_cop_action

N, MAX_STEPS = 7, 35


def _ensure_stack(g: dict) -> None:
    if "_squeeze" in g:
        return
    from cop_worker.rl.stall_squeeze import StallSqueeze

    g["_squeeze"] = StallSqueeze()
    chain = g.get("cop_chain", "hunt")
    if chain == "hunt":
        from cop_worker.rl.committed_hunt import CommittedHunt

        g["_plan"] = CommittedHunt()
    elif chain == "corridor":
        from cop_worker.rl.corridor_plan import CorridorPlan

        g["_plan"] = CorridorPlan()
    else:
        g["_plan"] = None


def cop_reply(g: dict, barriers: set, steps_left: int, move, cop_actions) -> tuple:
    """Choose and apply the model cop's action; returns (action, placed_cell)."""
    _ensure_stack(g)
    placed = None
    action = None
    if g["_plan"] is not None:
        if g.get("cop_chain", "hunt") == "corridor":
            action = g["_plan"].override(
                tuple(g["cop"]), tuple(g["thief"]), list(barriers),
                g["barriers_left"], g["step"], list(cop_actions),
            )  # fmt: skip
        else:
            action = g["_plan"].override(
                tuple(g["cop"]), tuple(g["thief"]), list(barriers),
                g["barriers_left"], steps_left, list(cop_actions),
            )  # fmt: skip
    if action is None and g.get("squeeze_on", True):
        action = g["_squeeze"].override(
            tuple(g["cop"]), tuple(g["thief"]), list(barriers),
            g["barriers_left"], steps_left, list(cop_actions),
        )  # fmt: skip
    if action is None:
        action = best_cop_action(
            tuple(g["cop"]),
            tuple(g["thief"]),
            barriers,
            g["barriers_left"],
            steps_left,
            time_budget_s=g["budget"],
        )
    if action in PLACE_DIRS and g["barriers_left"] > 0:
        dx, dy = PLACE_DIRS[action]
        cell = (g["cop"][0] + dx, g["cop"][1] + dy)
        if 0 <= cell[0] < N and 0 <= cell[1] < N and cell not in barriers:
            g["barriers"].append(list(cell))
            g["barriers_left"] -= 1
            placed = list(cell)
            if list(cell) == g["thief"]:
                g["over"], g["outcome"] = True, "capture"  # rule 46
    else:
        new = move(g["cop"], action, barriers)
        if new:
            g["cop"] = new
    return action, placed
