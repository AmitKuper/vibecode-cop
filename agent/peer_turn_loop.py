"""Peer turn loop: each agent drives its own side of the commit-reveal protocol.

No central judge exists. Both agents exchange COMMIT then REVEAL messages
directly via MCP. Each agent verifies the opponent's reveal immediately
after receiving it.

Phase sequence per turn:
  COMMIT_LOCAL → SEND_COMMIT → RECEIVE_OPPONENT_COMMIT →
  ACK →
  REVEAL_LOCAL → SEND_REVEAL → RECEIVE_OPPONENT_REVEAL →
  VERIFY_OPPONENT_REVEAL → APPLY_TURN
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from agent.mcp.crypto import create_commitment, hash_game_state
from agent.mcp.messages import ActionMessage
from agent.peer_audit import append_opponent_commit, append_opponent_reveal, verify_opponent_reveal
from agent.rules_engine import GameOutcome, RulesEngine

if TYPE_CHECKING:
    from agent.peer_runtime import PeerRuntime

logger = logging.getLogger(__name__)

_MOVE_ALIASES = {"N": "NORTH", "S": "SOUTH", "E": "EAST", "W": "WEST", "STAY": "STAY"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def _send_commit(runtime: "PeerRuntime", step: int, h_commit: str) -> dict | None:
    """Send our COMMIT to opponent and return the response."""
    msg = ActionMessage(
        game_id=runtime.game_id, step=step, role=runtime.role,
        config_sha256=runtime.config_sha256, timestamp=_now(),
        phase="commit", h_commit=h_commit,
    )
    try:
        resp = await runtime.opponent_client.action(runtime.game_id, msg)
        return resp
    except Exception as exc:
        logger.error(f"[PeerTurn] COMMIT send failed at step {step}: {exc}")
        return None


async def _send_reveal(runtime: "PeerRuntime", step: int, reveal_payload: dict) -> dict | None:
    """Send our REVEAL to opponent after both commits are exchanged."""
    msg = ActionMessage(
        game_id=runtime.game_id, step=step, role=runtime.role,
        config_sha256=runtime.config_sha256, timestamp=_now(),
        phase="reveal",
        move=reveal_payload["move"],
        hint=reveal_payload["hint"],
        intent=reveal_payload["intent"],
        state_hash=reveal_payload["state_hash"],
        nonces={str(step): reveal_payload["nonce"]},
    )
    try:
        resp = await runtime.opponent_client.action(runtime.game_id, msg)
        return resp
    except Exception as exc:
        logger.error(f"[PeerTurn] REVEAL send failed at step {step}: {exc}")
        return None


def _select_move(runtime: "PeerRuntime", board_state: dict) -> str:
    """Choose a move using the strategy layer (RL or heuristic fallback)."""
    try:
        if hasattr(runtime, "_select_move_rl") and callable(runtime._select_move_rl):
            obs = runtime._build_observation(board_state)
            move = runtime._select_move_rl(obs)
            if move:
                return move
    except Exception as exc:
        logger.warning(f"[PeerTurn] RL move selection failed: {exc}")

    # Heuristic: pick first legal move
    from agent.board import Board
    board = Board.from_dict(board_state)
    moves = board.get_legal_moves(runtime.role)
    return moves[0] if moves else "STAY"


def _build_board_state(runtime: "PeerRuntime") -> dict:
    """Snapshot current board as a plain dict for hashing."""
    b = runtime.board
    return {
        "cop_position": b.cop_position,
        "thief_position": b.thief_position,
        "turn": b.turn,
    }


async def run_peer_turn(
    runtime: "PeerRuntime",
    step: int,
    rules: RulesEngine,
) -> tuple[str | None, str | None]:
    """Execute one full commit-reveal turn from this agent's perspective.

    Returns:
        (winner_or_None, abort_reason_or_None) — non-None means game over.
    """
    board_state = _build_board_state(runtime)
    state_hash = hash_game_state(board_state)
    move = _select_move(runtime, {**board_state, "scent_field": rules.get_scent_field()})
    hint = f"Moving {move}"
    intent = "truth"

    # --- COMMIT_LOCAL + SEND_COMMIT ---
    h_commit, nonce = create_commitment(
        game_id=runtime.game_id, step=step, role=runtime.role,
        state_hash=state_hash, move=move, hint=hint, intent=intent,
    )
    runtime._store_my_commit(step, {
        "h_commit": h_commit, "nonce": nonce,
        "move": move, "hint": hint, "intent": intent, "state_hash": state_hash,
    })
    logger.info(f"[PeerTurn] step={step} committed move={move} h={h_commit[:12]}...")

    opponent_resp = await _send_commit(runtime, step, h_commit)
    if not opponent_resp:
        return None, f"COMMIT exchange failed at step {step} (send error)"

    # RECEIVE_OPPONENT_COMMIT — opponent returns their h_commit in the response
    opp_h_commit = opponent_resp.get("h_commit")
    if not opp_h_commit:
        return None, f"Opponent did not return h_commit at step {step}"
    append_opponent_commit(runtime.game_dir, step, opp_h_commit)
    logger.debug(f"[PeerTurn] step={step} stored opponent h_commit={opp_h_commit[:12]}...")

    # --- REVEAL_LOCAL + SEND_REVEAL ---
    reveal_payload = {"move": move, "hint": hint, "intent": intent,
                      "state_hash": state_hash, "nonce": nonce}
    opp_reveal_resp = await _send_reveal(runtime, step, reveal_payload)
    if not opp_reveal_resp:
        return None, f"REVEAL exchange failed at step {step} (send error)"

    # RECEIVE_OPPONENT_REVEAL
    opp_move_short = opp_reveal_resp.get("move")
    if not opp_move_short:
        return None, f"Opponent did not include move in REVEAL at step {step}"

    opp_reveal = {
        "move": opp_move_short,
        "hint": opp_reveal_resp.get("hint", ""),
        "intent": opp_reveal_resp.get("intent", "truth"),
        "state_hash": opp_reveal_resp.get("state_hash", ""),
    }
    # Extract nonce from opponent reveal response (sent as {step: nonce} dict)
    opp_nonces = opp_reveal_resp.get("nonces", {})
    opp_nonce = opp_nonces.get(str(step)) or opp_reveal_resp.get("nonce")
    if not opp_nonce:
        return None, f"Opponent did not include nonce in REVEAL at step {step}"

    # VERIFY_OPPONENT_REVEAL — local cryptographic check, no judge needed
    opp_reveal_with_nonce = {**opp_reveal, "nonce": opp_nonce}
    ok = verify_opponent_reveal(
        opp_h_commit, opp_reveal_with_nonce,
        runtime.game_id, step, runtime.opponent_role,
    )
    if not ok:
        logger.error(f"[PeerTurn] TAMPER DETECTED at step {step}: opponent commitment mismatch")
        return "technical_loss", f"Commitment mismatch at step {step}"

    append_opponent_reveal(runtime.game_dir, step, opp_reveal)

    # --- APPLY_TURN ---
    my_move = _MOVE_ALIASES.get(move, move)
    opp_move = _MOVE_ALIASES.get(opp_move_short, opp_move_short)

    if runtime.role == "cop":
        cop_move, thief_move = my_move, opp_move
    else:
        cop_move, thief_move = opp_move, my_move

    if not rules.validate_move("cop", cop_move):
        logger.warning(f"[PeerTurn] Invalid cop move {cop_move!r} at step {step}, using STAY")
        cop_move = "STAY"
    if not rules.validate_move("thief", thief_move):
        logger.warning(f"[PeerTurn] Invalid thief move {thief_move!r} at step {step}, using STAY")
        thief_move = "STAY"

    rules.apply_moves(cop_move, thief_move)
    logger.info(
        f"[PeerTurn] step={step} cop={cop_move} thief={thief_move} "
        f"cop_pos={runtime.board.cop_position} thief_pos={runtime.board.thief_position}"
    )

    outcome = rules.check_game_status()
    if outcome == GameOutcome.COP_WIN:
        return "cop", None
    if outcome == GameOutcome.THIEF_WIN:
        return "thief", None
    return None, None


def _get_watchdog_timeout() -> float:
    """Load watchdog timeout from shared config, defaulting to 60s."""
    try:
        from agent.config.shared_config import load_shared_config
        cfg = load_shared_config()
        return float(cfg.get("network_and_league", {}).get("watchdog_timeout_sec", 60))
    except Exception:
        return 60.0


async def run_peer_turn_loop(
    runtime: "PeerRuntime",
    rules: RulesEngine,
    max_turns: int,
) -> tuple[str | None, str | None, int]:
    """Run all turns for this agent's side of the game.

    Returns:
        (winner, abort_reason, final_step)
    """
    winner = None
    abort_reason = None
    final_step = 0
    watchdog_timeout = _get_watchdog_timeout()

    try:
        for step in range(1, max_turns + 1):
            final_step = step
            try:
                winner, abort_reason = await asyncio.wait_for(
                    run_peer_turn(runtime, step, rules),
                    timeout=watchdog_timeout,
                )
            except asyncio.TimeoutError:
                abort_reason = f"Watchdog timeout at step {step}"
                logger.error(f"[PeerTurnLoop] {abort_reason}")
                break
            if winner is not None or abort_reason is not None:
                break
    except Exception as exc:
        logger.error(f"[PeerTurnLoop] Unexpected error: {exc}", exc_info=True)
        abort_reason = str(exc)

    if winner is None and abort_reason is None:
        winner = "thief"  # thief survives max_turns

    return winner, abort_reason, final_step
