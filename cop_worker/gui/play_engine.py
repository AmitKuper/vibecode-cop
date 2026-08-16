"""Game state + physics + the model's half-move for human-vs-model play.

The movement tables and legality come from the same modules the engine
searches over (action_space, pursuit_eval), so the human plays exactly the
game the model is optimizing.
"""

from __future__ import annotations

from cop_worker.rl.action_space import PLACE_DIRS
from cop_worker.rl.pursuit_search import best_cop_action, best_thief_action

_GAMES: dict = {}
N, MAX_STEPS, BARRIERS = 7, 35, 14
MOVES = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0), "STAY": (0, 0)}


def _state(g: dict) -> dict:
    return {
        k: g[k]
        for k in (
            "id",
            "human_role",
            "step",
            "cop",
            "thief",
            "barriers",
            "barriers_left",
            "over",
            "outcome",
            "scent_thief",
            "scent_cop",
        )
    }


def _move(pos: list, action: str, barriers: set) -> list | None:
    dx, dy = MOVES.get(action, (None, None))
    if dx is None:
        return None
    nx, ny = pos[0] + dx, pos[1] + dy
    if not (0 <= nx < N and 0 <= ny < N) or (nx, ny) in barriers:
        return None
    return [nx, ny]


def _emit(g: dict, role: str) -> None:
    trail = g[f"_trail_{role}"]
    pos = g["thief"] if role == "thief" else g["cop"]
    g[f"scent_{role}"] = trail.full_turn((pos[1], pos[0]))


def _model_reply(g: dict) -> None:
    """The engine's half-move (and outcome checks), using production search."""
    barriers = set(map(tuple, g["barriers"]))
    steps_left = MAX_STEPS - g["step"] + 1
    if g["human_role"] == "cop":
        action = best_thief_action(
            tuple(g["cop"]),
            tuple(g["thief"]),
            barriers,
            steps_left,
            cop_barriers_left=g["barriers_left"],
            time_budget_s=g["budget"],
        )
        new = _move(g["thief"], action, barriers)
        if new:
            g["thief"] = new
        _emit(g, "thief")
        if g["thief"] == g["cop"]:
            g["over"], g["outcome"] = True, "capture"
    else:
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
                if list(cell) == g["thief"]:
                    g["over"], g["outcome"] = True, "capture"  # rule 46
        else:
            new = _move(g["cop"], action, barriers)
            if new:
                g["cop"] = new
        _emit(g, "cop")
        if g["cop"] == g["thief"]:
            g["over"], g["outcome"] = True, "capture"
    g["last_model_action"] = action
