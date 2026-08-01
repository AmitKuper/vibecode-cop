"""Peer turn loop: each agent drives its own side of the commit-reveal protocol.

No central judge exists. Both agents exchange COMMIT then REVEAL messages
directly via MCP. Each agent verifies the opponent's reveal immediately
after receiving it.

Phase sequence per turn:
  COMMIT_LOCAL → SEND_COMMIT → RECEIVE_OPPONENT_COMMIT →
  REVEAL_LOCAL → SEND_REVEAL → RECEIVE_OPPONENT_REVEAL →
  VERIFY_OPPONENT_REVEAL → APPLY_TURN
"""

import asyncio
import logging
from typing import TYPE_CHECKING

from agent.mcp.crypto import create_commitment, hash_game_state
from agent.peer_audit import append_opponent_commit, append_opponent_reveal
from agent.peer_turn_helpers import (
    _MOVE_ALIASES,
    build_board_state,
    get_watchdog_timeout,
    select_move,
    send_commit,
    send_reveal,
)
from agent.rl.env_helpers import apply_place_action
from agent.rules_engine import GameOutcome, RulesEngine

if TYPE_CHECKING:
    from agent.peer_runtime import PeerRuntime

logger = logging.getLogger(__name__)


async def run_peer_turn(
    runtime: "PeerRuntime",
    step: int,
    rules: RulesEngine,
) -> tuple[str | None, str | None]:
    """Execute one full commit-reveal turn from this agent's perspective.

    Returns:
        (winner_or_None, abort_reason_or_None) — non-None means game over.
    """
    board_state = build_board_state(runtime)
    state_hash = hash_game_state(board_state)
    move = await select_move(runtime, {**board_state, "scent_field": rules.get_scent_field()})
    hint = f"Moving {move}"
    intent = "truth"

    h_commit, nonce = create_commitment(
        game_id=runtime.game_id, step=step, role=runtime.role,
        state_hash=state_hash, move=move, hint=hint, intent=intent,
    )
    runtime._store_my_commit(step, {
        "h_commit": h_commit, "nonce": nonce,
        "move": move, "hint": hint, "intent": intent, "state_hash": state_hash,
    })
    logger.info(f"[PeerTurn] step={step} committed move={move} h={h_commit[:12]}...")

    opponent_resp = await send_commit(runtime, step, h_commit)
    if not opponent_resp:
        return None, f"COMMIT exchange failed at step {step} (send error)"
    opp_h_commit = opponent_resp.get("h_commit")
    if not opp_h_commit:
        return None, f"Opponent did not return h_commit at step {step}"
    append_opponent_commit(runtime.game_dir, step, opp_h_commit)
    logger.debug(f"[PeerTurn] step={step} stored opponent h_commit={opp_h_commit[:12]}...")

    reveal_payload = {"move": move, "hint": hint, "intent": intent,
                      "state_hash": state_hash, "nonce": nonce}
    opp_reveal_resp = await send_reveal(runtime, step, reveal_payload)
    if not opp_reveal_resp:
        return None, f"REVEAL exchange failed at step {step} (send error)"
    opp_move_short = opp_reveal_resp.get("move")
    if not opp_move_short:
        return None, f"Opponent did not include move in REVEAL at step {step}"

    opp_reveal = {
        "move": opp_move_short, "hint": opp_reveal_resp.get("hint", ""),
        "intent": opp_reveal_resp.get("intent", "truth"),
        "state_hash": opp_reveal_resp.get("state_hash", ""),
    }
    append_opponent_reveal(runtime.game_dir, step, opp_reveal)

    my_move = _MOVE_ALIASES.get(move, move)
    opp_move = _MOVE_ALIASES.get(opp_move_short, opp_move_short)
    cop_move, thief_move = (my_move, opp_move) if runtime.role == "cop" else (opp_move, my_move)

    # Handle barrier placement: PLACE_* places a barrier then cop stays.
    if cop_move.startswith("PLACE_"):
        barriers_remaining = getattr(runtime, "_cop_barriers_remaining", 14)
        new_remaining = apply_place_action(
            runtime.board, cop_move, runtime.board.grid_size, barriers_remaining
        )
        runtime._cop_barriers_remaining = new_remaining
        cop_move = "STAY"
        if list(runtime.board.thief_position) in runtime.board.barriers:
            runtime.board.turn += 1
            return "cop", None

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


async def run_peer_turn_loop(
    runtime: "PeerRuntime",
    rules: RulesEngine,
    max_turns: int,
) -> tuple[str | None, str | None, int]:
    """Run all turns for this agent's side of the game.

    Returns:
        (winner, abort_reason, final_step)
    """
    winner = abort_reason = None
    final_step = 0
    watchdog_timeout = get_watchdog_timeout()
    try:
        for step in range(1, max_turns + 1):
            final_step = step
            try:
                winner, abort_reason = await asyncio.wait_for(
                    run_peer_turn(runtime, step, rules), timeout=watchdog_timeout,
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
        winner = "thief"
    return winner, abort_reason, final_step
