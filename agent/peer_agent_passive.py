"""Passive-mode (thief) helpers for PeerAgentRuntime.

Handles commit, reveal, and final_audit phases for the passive side.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agent.board import Board
from agent.language.hints import generate_hint as _generate_hint_fallback
from agent.peer_runtime_io import _load_start_positions
from agent.rules_engine import RulesEngine

if TYPE_CHECKING:
    from agent.peer_runtime import PeerRuntime

logger = logging.getLogger(__name__)

_MOVE_ALIASES = {"N": "NORTH", "S": "SOUTH", "E": "EAST", "W": "WEST", "STAY": "STAY"}


def _generate_hint(move: str, board=None, step: int = 0, belief_entropy: float = 1.0) -> str:
    """Generate hint using NaturalLanguagePolicy (symmetric with active side)."""
    try:
        from agent.language.deception_policy import NaturalLanguagePolicy

        role = "thief"  # passive side is thief in standard P2P config
        policy = NaturalLanguagePolicy(role)
        intent = policy.choose_intent(step=step, belief_entropy=belief_entropy)
        return policy.generate(move, intent)
    except Exception:
        return _generate_hint_fallback(move)


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
    from agent.domain.runtime_transition import legal_actions_for_role

    rules = rules_ref[0] if rules_ref else RulesEngine(rt.board, max_turns=rt.max_turns)
    legal = legal_actions_for_role(rt, rules, rt.role)
    if rt.counted_mode:
        if rt.orchestrator is None or not rt.rl_model_loaded:
            raise RuntimeError("counted recurrent movement policy is unavailable")
        own_position = tuple(rt.board.cop_position if rt.role == "cop" else rt.board.thief_position)
        move = rt.orchestrator.select_trained_move(
            own_position=own_position,
            barriers=[tuple(item) for item in rt.board.barriers],
            barriers_remaining=rt._cop_barriers_remaining if rt.role == "cop" else 0,
            legal_actions=legal,
            step=message.step,
            gamelet=rt._gamelet_number(game_id),
            last_hint=rt._last_opponent_hint,
        )
    else:
        move = rt._select_move_rl(rt._build_observation(board_state))
        if not move:
            move = legal[0]
    selected = {"NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W"}.get(move, move)
    if selected not in legal:
        if rt.counted_mode:
            raise RuntimeError(f"Counted policy selected illegal action {move!r}")
        selected = legal[0]
    move = selected
    # Use orchestrator's symmetric language policy if available
    _orch = getattr(rt, "orchestrator", None)
    if _orch is not None:
        try:
            hint, intent = _orch.generate_strategic_hint(move, step=message.step)
        except Exception:
            hint = _generate_hint(move, rt.board, step=message.step)
            intent = "truth"
    else:
        hint = _generate_hint(move, rt.board, step=message.step)
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
    from agent.domain.runtime_transition import IllegalJointActionError, apply_runtime_transition
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

    raw_opp_move = message.move or "STAY"
    opp_move = _MOVE_ALIASES.get(raw_opp_move, raw_opp_move)
    my_move = _MOVE_ALIASES.get(payload["move"], payload["move"])
    cop_move, thief_move = (opp_move, my_move) if rt.role == "thief" else (my_move, opp_move)

    rules = rules_ref[0] if rules_ref else RulesEngine(rt.board, max_turns=rt.max_turns)

    try:
        transition = apply_runtime_transition(rt, rules, cop_move, thief_move)
    except IllegalJointActionError as exc:
        return {"ok": False, "error": f"Protocol violation: {exc}"}

    rt._last_opponent_hint = opp_reveal["hint"]
    if rt.orchestrator is not None:
        rt.orchestrator.update_scent_and_belief(
            tuple(rt.board.cop_position),
            tuple(rt.board.thief_position),
            [tuple(item) for item in rt.board.barriers],
        )
        rt.orchestrator.record_step_evidence(
            gamelet=rt._gamelet_number(game_id),
            step=message.step,
            local_commitment=payload["h_commit"],
            local_move=payload["move"],
            received_move=raw_opp_move,
        )

    return {
        "ok": True,
        "phase": "reveal",
        "move": payload["move"],
        "hint": payload["hint"],
        "intent": payload["intent"],
        "state_hash": payload["state_hash"],
        "captured": transition.capture or transition.trapped,
    }


def handle_passive_final_audit(rt: PeerRuntime, game_id: str, message) -> dict:
    """Handle final_audit on the passive side.

    Runs local audit with received opponent nonces, creates and signs AuditSummary,
    returns own nonces + signed AuditSummary for bilateral consensus.
    """
    import hashlib
    import json
    import time

    from agent.audit.audit_summary import AuditSummary, create_signed_audit_summary
    from agent.mcp.coordinator import gamelet_from_game_id
    from agent.peer_audit import load_opponent_commits, run_final_audit
    from agent.step0.declaration import SignedDeclaration
    from agent.step0.signing import generate_key_pair

    # 1. Return own nonces
    my_nonces = {str(s): p["nonce"] for s, p in rt._my_commits.items()}

    # 2. Run local audit with opponent's nonces
    opp_role = "cop" if rt.role == "thief" else "thief"
    opp_nonces_raw = getattr(message, "nonces", {}) or {}
    opp_nonces = {int(k): v for k, v in opp_nonces_raw.items()}
    audit_ok, details = run_final_audit(rt.game_dir, game_id, opp_role, opp_nonces)

    # 3. Create signed AuditSummary
    priv_key = getattr(rt, "_signing_private_key", None)
    pub_key = getattr(rt, "_signing_public_key", None)
    if not isinstance(priv_key, bytes) or not isinstance(pub_key, bytes):
        priv_key, pub_key = generate_key_pair()
    pub_hex = pub_key.hex()
    audit_status = details.get("audit_status", "NOT_APPLICABLE")
    gamelet = rt._gamelet_number(game_id)
    if not isinstance(gamelet, int):
        gamelet = gamelet_from_game_id(game_id)
    local_step0 = rt._local_step0.get(game_id)
    declaration_hash = ""
    if isinstance(local_step0, SignedDeclaration):
        declaration_hash = local_step0.declaration.declaration_hash()
    transcript_root = rt.orchestrator.get_journal(gamelet).transcript_root()
    if not isinstance(transcript_root, str):
        transcript_root = ""
    final_state_hash = hashlib.sha256(
        json.dumps(rt.board.to_dict(), sort_keys=True, default=str).encode()
    ).hexdigest()
    summary = AuditSummary(
        game_uid=game_id,
        gamelet=gamelet,
        transcript_root=transcript_root,
        declaration_hash=declaration_hash,
        config_hash=rt.config_sha256 if isinstance(rt.config_sha256, str) else "",
        expected_steps=len(load_opponent_commits(rt.game_dir)),
        verified_steps=sum(1 for k, v in details.items() if k.startswith("step_") and v == "ok"),
        audit_status=audit_status,
        mismatch_evidence="" if audit_ok else str(details),
        local_final_state_hash=final_state_hash,
        timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        signing_key_id=(
            rt._signing_key_id if isinstance(rt._signing_key_id, str) else "legacy-ephemeral"
        ),
        public_key_hex=pub_hex,
    )
    signed = create_signed_audit_summary(summary, priv_key)
    rt._local_audit_summaries[game_id] = signed

    return {
        "ok": True,
        "phase": "final_audit",
        "nonces": my_nonces,
        "signed_audit_summary": json.dumps(signed.to_dict()),
        "audit_ok": audit_ok,
    }
