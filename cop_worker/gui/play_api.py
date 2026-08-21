"""Human-vs-model play: measure the production engine's strength by hand.

The model side is the EXACT counted engine - best_cop_action /
best_thief_action (hybrid minimax, production defaults depth=4, 10s budget;
a faster budget is offered for casual play, clearly labelled). Physics uses
the same movement tables the engine itself searches over, so the game the
human plays is the game the engine thinks it is playing.

Local-only and stateless across restarts: games live in memory, nothing is
recorded, and this router exists only where the engine does (the cop repo) -
the hub feature-detects it via /api/play/available.
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from cop_worker.gui.play_engine import (
    _GAMES,
    BARRIERS,
    MAX_STEPS,
    N,
    _emit,
    _model_reply,
    _move,
    _state,
)
from cop_worker.gui.play_record import note, persist_if_over
from cop_worker.rl.action_space import PLACE_DIRS
from cop_worker.rl.pursuit_eval import _legal_moves
from cop_worker.scent_chebyshev import ChebyshevTrail

router = APIRouter()


@router.get("/api/play/available")
async def available() -> JSONResponse:
    return JSONResponse({"ok": True, "budgets": {"fast": 2.0, "production": 10.0}})


@router.post("/api/play/new")
async def new_game(body: dict) -> JSONResponse:
    role = body.get("role", "cop")
    if role not in ("cop", "thief"):
        return JSONResponse({"error": "role must be cop or thief"}, status_code=400)
    g = {
        "id": secrets.token_hex(8),
        "human_role": role,
        "step": 1,
        "cop": [0, 0],
        "thief": [3, 3],
        "barriers": [],
        "barriers_left": BARRIERS,
        "over": False,
        "outcome": None,
        "scent_thief": {},
        "scent_cop": {},
        "budget": float(body.get("budget", 10.0)),
        "_trail_thief": ChebyshevTrail(N),
        "_trail_cop": ChebyshevTrail(N),
    }
    _GAMES[g["id"]] = g
    if role == "cop":  # thief moves first every step: model opens
        _model_reply(g)
    persist_if_over(g)
    resp = _state(g)
    resp["last_model_action"] = g.get("last_model_action")
    return JSONResponse(resp)


@router.post("/api/play/move")
async def play_move(body: dict) -> JSONResponse:
    g = _GAMES.get(body.get("game", ""))
    if g is None:
        return JSONResponse({"error": "unknown game"}, status_code=404)
    if g["over"]:
        return JSONResponse(_state(g))
    action = str(body.get("action", "")).upper()
    barriers = set(map(tuple, g["barriers"]))
    if g["human_role"] == "cop":
        placed = None
        if action in PLACE_DIRS:
            dx, dy = PLACE_DIRS[action]
            cell = (g["cop"][0] + dx, g["cop"][1] + dy)
            if (
                g["barriers_left"] <= 0
                or not (0 <= cell[0] < N and 0 <= cell[1] < N)
                or cell in barriers
            ):
                return JSONResponse({"error": "illegal barrier placement"}, status_code=400)
            g["barriers"].append(list(cell))
            g["barriers_left"] -= 1
            placed = list(cell)
            if list(cell) == g["thief"]:
                g["over"], g["outcome"] = True, "capture"
        else:
            new = _move(g["cop"], action, barriers)
            if new is None:
                return JSONResponse({"error": "illegal move"}, status_code=400)
            g["cop"] = new
        _emit(g, "cop")
        note(g, "human", "cop", action, placed)
        if g["cop"] == g["thief"]:
            g["over"], g["outcome"] = True, "capture"
    else:
        legal = {a for a, _ in _legal_moves(tuple(g["thief"]), barriers, N)}
        if action not in legal:
            return JSONResponse({"error": "illegal move"}, status_code=400)
        new = _move(g["thief"], action, barriers)
        g["thief"] = new if new else g["thief"]
        _emit(g, "thief")
        note(g, "human", "thief", action)
        if g["thief"] == g["cop"]:
            g["over"], g["outcome"] = True, "capture"
    # round complete when the second mover has played; thief always moves first
    if not g["over"]:
        if g["human_role"] == "thief":
            _model_reply(g)  # cop answers within the same step
        if not g["over"]:
            g["step"] += 1
            if g["step"] > MAX_STEPS:
                g["over"], g["outcome"] = True, "survival"
            elif g["human_role"] == "cop":
                _model_reply(g)  # next step opens with the model thief
                if not g["over"] and g["step"] > MAX_STEPS:
                    g["over"], g["outcome"] = True, "survival"
    persist_if_over(g)
    resp = _state(g)
    resp["last_model_action"] = g.get("last_model_action")
    resp["record_file"] = g.get("record_file")
    return JSONResponse(resp)
