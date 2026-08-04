"""Passive-mode (thief) helpers for PeerAgentRuntime.

Handles commit, reveal, and final_audit phases for the passive side.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agent.board import Board
from agent.language.hints import generate_hint as _generate_hint_fn
from agent.peer_runtime_io import _load_start_positions
from agent.rules_engine import RulesEngine

if TYPE_CHECKING:
    from agent.peer_runtime import PeerRuntime

logger = logging.getLogger(__name__)

_MOVE_ALIASES = {"N": "NORTH", "S": "SOUTH", "E": "EAST", "W": "WEST", "STAY": "STAY"}


def _generate_hint(move: str, board=None) -> str:
    return _generate_hint_fn(move)


def init_passive_game(rt: PeerRuntime, game_id: str, rules_ref: list) -> None:
    """Set up PeerRuntime state for a passive (thief) game. Idempotent per game_id."""
    if rt.game_id == game_id:
        return
    rt.game_id = game_id
    rt.game_dir = rt.games_dir / game_id
    rt.game_dir.mkdir(parents=True, exist_ok=True)
    rt._my_commits = {}
    rt._cop_barriers_remaining = 14  # track cop's barrier quota on passive side
    cop_start, thief_start = _load_start_positions()
    rt.board = Board(cop_position=cop_start, thief_position=thief_start)
    rules_ref.clear()
    rules_ref.append(RulesEngine(rt.board, max_turns=rt.max_turns))
    logger.info(f"[PeerAgentRuntime/{rt.role}] Passive game {game_id} initialised")


def handle_passive_commit(rt: PeerRuntime, game_id: str, message, rules_ref: list) -> dict:
    """Generate own commitment when cop sends its commit (thief passive mode)."""
    from agent.mcp.crypto import create_commitment, hash_game_state

    if rt.game_id != game_id:
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
    hint = _generate_hint(move, rt.board)
    intent = "truth"
    h_commit, nonce = create_commitment(
        game_id=game_id,
        step=message.step,
        role=rt.role,
        state_hash=state_hash,
        move=move,
        hint=hint,
        intent=intent,
    )
    rt._store_my_commit(
        message.step,
        {
            "h_commit": h_commit,
            "nonce": nonce,
            "move": move,
            "hint": hint,
            "intent": intent,
            "state_hash": state_hash,
        },
    )
    logger.info(
        f"[PeerAgentRuntime/{rt.role}] Committed step={message.step} "
        f"move={move} h={h_commit[:12]}..."
    )
    # NOTE: coordinator advance (COMMIT_RECEIVED → BOTH_COMMITTED) is handled
    # in server_handlers.handle_action() after this callback returns h_commit.
    return {"ok": True, "phase": "commit", "h_commit": h_commit}


def handle_passive_reveal(rt: PeerRuntime, game_id: str, message, rules_ref: list) -> dict:
    """Return own reveal when cop sends its reveal; apply moves to local board."""
    from agent.peer_audit import append_opponent_reveal
    from agent.rl.env_helpers import apply_place_action

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

    raw_opp_move = message.move or "STAY"
    opp_move = _MOVE_ALIASES.get(raw_opp_move, raw_opp_move)
    my_move = _MOVE_ALIASES.get(payload["move"], payload["move"])
    cop_move, thief_move = (opp_move, my_move) if rt.role == "thief" else (my_move, opp_move)

    rules = rules_ref[0] if rules_ref else RulesEngine(rt.board, max_turns=rt.max_turns)

    # Handle cop barrier placement: PLACE_* places a barrier then cop stays.
    if cop_move.startswith("PLACE_"):
        barriers_remaining = getattr(rt, "_cop_barriers_remaining", 14)
        new_remaining = apply_place_action(
            rt.board, cop_move, rt.board.grid_size, barriers_remaining
        )
        rt._cop_barriers_remaining = new_remaining
        cop_move = "STAY"
        if list(rt.board.thief_position) in rt.board.barriers:
            rt.board.turn += 1
            return {
                "ok": True,
                "phase": "reveal",
                "move": payload["move"],
                "hint": payload["hint"],
                "intent": payload["intent"],
                "state_hash": payload["state_hash"],
                "captured": True,
            }

    if rules.validate_move("cop", cop_move) and rules.validate_move("thief", thief_move):
        rules.apply_moves(cop_move, thief_move)

    return {
        "ok": True,
        "phase": "reveal",
        "move": payload["move"],
        "hint": payload["hint"],
        "intent": payload["intent"],
        "state_hash": payload["state_hash"],
    }


def handle_passive_final_audit(rt: PeerRuntime, game_id: str, message) -> dict:
    """Handle final_audit on the passive side.

    Runs local audit with received opponent nonces, creates and signs AuditSummary,
    returns own nonces + signed AuditSummary for bilateral consensus.
    """
    import time

    from agent.audit.audit_summary import AuditSummary, create_signed_audit_summary
    from agent.peer_audit import run_final_audit
    from agent.step0.signing import generate_key_pair

    # 1. Return own nonces
    my_nonces = {str(s): p["nonce"] for s, p in rt._my_commits.items()}

    # 2. Run local audit with opponent's nonces
    opp_role = "cop" if rt.role == "thief" else "thief"
    opp_nonces_raw = getattr(message, "nonces", {}) or {}
    opp_nonces = {int(k): v for k, v in opp_nonces_raw.items()}
    audit_ok, details = run_final_audit(rt.game_dir, game_id, opp_role, opp_nonces)

    # 3. Create signed AuditSummary
    priv_key, pub_key = generate_key_pair()
    pub_hex = pub_key.hex()
    audit_status = details.get("audit_status", "NOT_APPLICABLE")
    summary = AuditSummary(
        game_uid=game_id,
        gamelet=0,
        expected_steps=len(rt._my_commits),
        verified_steps=sum(1 for v in details.values() if v == "ok"),
        audit_status=audit_status,
        mismatch_evidence="" if audit_ok else str(details),
        timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        public_key_hex=pub_hex,
    )
    signed = create_signed_audit_summary(summary, priv_key)

    import json

    return {
        "ok": True,
        "phase": "final_audit",
        "nonces": my_nonces,
        "signed_audit_summary": json.dumps(signed.to_dict()),
    }
