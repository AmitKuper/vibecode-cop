"""Passive-mode (thief) helpers for PeerAgentRuntime."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from agent.board import Board
from agent.peer_runtime import _load_start_positions
from agent.rules_engine import RulesEngine

if TYPE_CHECKING:
    from agent.peer_runtime import PeerRuntime

logger = logging.getLogger(__name__)

_MOVE_ALIASES = {"N": "NORTH", "S": "SOUTH", "E": "EAST", "W": "WEST", "STAY": "STAY"}


def init_passive_game(rt: "PeerRuntime", game_id: str, rules_ref: list) -> None:
    """Set up PeerRuntime state for a passive (thief) game."""
    rt.game_id = game_id
    rt.game_dir = rt.games_dir / game_id
    rt.game_dir.mkdir(parents=True, exist_ok=True)
    rt._my_commits = {}
    cop_start, thief_start = _load_start_positions()
    rt.board = Board(cop_position=cop_start, thief_position=thief_start)
    rules_ref.clear()
    rules_ref.append(RulesEngine(rt.board, max_turns=rt.max_turns))
    logger.info(f"[PeerAgentRuntime/{rt.role}] Passive game {game_id} initialised")


def handle_passive_commit(rt: "PeerRuntime", game_id: str, message, rules_ref: list) -> dict:
    """Generate own commitment when cop sends its commit (thief passive mode)."""
    from agent.mcp.crypto import create_commitment, hash_game_state
    if not rt.game_id:
        init_passive_game(rt, game_id, rules_ref)

    board_state = {
        "cop_position": rt.board.cop_position,
        "thief_position": rt.board.thief_position,
        "turn": rt.board.turn,
    }
    state_hash = hash_game_state(board_state)
    move = rt._select_move_rl(rt._build_observation(board_state))
    if not move:
        legal = rt.board.get_legal_moves(rt.role)
        move = legal[0] if legal else "STAY"
    hint = f"Moving {move}"
    intent = "truth"
    h_commit, nonce = create_commitment(
        game_id=game_id, step=message.step, role=rt.role,
        state_hash=state_hash, move=move, hint=hint, intent=intent,
    )
    rt._store_my_commit(message.step, {
        "h_commit": h_commit, "nonce": nonce,
        "move": move, "hint": hint, "intent": intent, "state_hash": state_hash,
    })
    logger.info(
        f"[PeerAgentRuntime/{rt.role}] Committed step={message.step} "
        f"move={move} h={h_commit[:12]}..."
    )
    return {"ok": True, "phase": "commit", "h_commit": h_commit}


def handle_passive_reveal(rt: "PeerRuntime", game_id: str, message, rules_ref: list) -> dict:
    """Return own reveal when cop sends its reveal; apply moves to local board."""
    from agent.peer_audit import append_opponent_reveal
    payload = rt._my_commits.get(message.step)
    if not payload:
        return {"ok": False, "error": f"No commit payload for step {message.step}"}

    opp_reveal = {
        "move": message.move or "STAY",
        "hint": getattr(message, "hint", "") or "",
        "intent": getattr(message, "intent", "truth") or "truth",
        "state_hash": getattr(message, "state_hash", "") or "",
    }
    append_opponent_reveal(rt.game_dir, message.step, opp_reveal)

    opp_move = _MOVE_ALIASES.get(message.move or "STAY", message.move or "STAY")
    my_move = _MOVE_ALIASES.get(payload["move"], payload["move"])
    cop_move, thief_move = (opp_move, my_move) if rt.role == "thief" else (my_move, opp_move)

    rules = rules_ref[0] if rules_ref else RulesEngine(rt.board, max_turns=rt.max_turns)
    if rules.validate_move("cop", cop_move) and rules.validate_move("thief", thief_move):
        rules.apply_moves(cop_move, thief_move)

    return {
        "ok": True, "phase": "reveal",
        "move": payload["move"], "hint": payload["hint"],
        "intent": payload["intent"], "state_hash": payload["state_hash"],
    }
