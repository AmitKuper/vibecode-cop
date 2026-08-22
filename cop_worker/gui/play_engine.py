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


def _rule47(g: dict) -> None:
    """Enclosure capture, matching the production domain: a thief with no
    legal NON-STAY move is captured where it stands (STAY does not rescue)."""
    from cop_worker.rl.pursuit_eval import _legal_moves

    if g["over"]:
        return
    walls = set(map(tuple, g["barriers"]))
    if not any(a != "STAY" for a, _ in _legal_moves(tuple(g["thief"]), walls, N)):
        g["over"], g["outcome"] = True, "capture"


def _model_reply(g: dict) -> None:
    """The engine's half-move — the FULL champion stack, not bare minimax:
    thief = minimax + confined-mode escape; cop = corridor plan >
    stall-squeeze > minimax (the wire player's exact priority chain)."""
    from cop_worker.gui.play_record import note
    from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS

    placed = None
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
        if "_escape" not in g:
            from cop_worker.rl.line_escape import LineEscape

            g["_escape"] = LineEscape()
        override = g["_escape"].override(
            tuple(g["thief"]), tuple(g["cop"]), list(barriers),
            g["barriers_left"], steps_left, action, list(THIEF_ACTIONS),
        )  # fmt: skip
        action = override or action
        new = _move(g["thief"], action, barriers)
        if new:
            g["thief"] = new
        _emit(g, "thief")
        if g["thief"] == g["cop"]:
            g["over"], g["outcome"] = True, "capture"
    else:
        if "_hunt" not in g:
            from cop_worker.rl.committed_hunt import CommittedHunt
            from cop_worker.rl.stall_squeeze import StallSqueeze

            # GUI fields the COMMITTED-HUNT cop (operator playbook): it is
            # the only cop that captures our own thief class (@31) — the
            # operator, playing thief, is its acceptance test. The counted
            # wire chain keeps the corridor default (see search_policy).
            g["_hunt"], g["_squeeze"] = CommittedHunt(), StallSqueeze()
        action = g["_hunt"].override(
            tuple(g["cop"]), tuple(g["thief"]), list(barriers),
            g["barriers_left"], steps_left, list(COP_ACTIONS),
        )  # fmt: skip
        if action is None:
            action = g["_squeeze"].override(
                tuple(g["cop"]), tuple(g["thief"]), list(barriers),
                g["barriers_left"], steps_left, list(COP_ACTIONS),
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
            new = _move(g["cop"], action, barriers)
            if new:
                g["cop"] = new
        _emit(g, "cop")
        if g["cop"] == g["thief"]:
            g["over"], g["outcome"] = True, "capture"
    g["last_model_action"] = action
    _rule47(g)
    note(g, "model", "thief" if g["human_role"] == "cop" else "cop", action, placed)
