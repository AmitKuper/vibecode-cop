"""Per-turn commit/reveal protocol helpers for GameRunner."""

import asyncio
import logging
from datetime import UTC, datetime

from agent.mcp.client import GameMCPClient
from agent.mcp.messages import ActionMessage
from agent.rules_engine import GameOutcome, RulesEngine

logger = logging.getLogger(__name__)
_SHORT_TO_LONG = {"N": "NORTH", "S": "SOUTH", "E": "EAST", "W": "WEST", "STAY": "STAY"}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def request_commit(
    runner: object, client: GameMCPClient, game_id: str, step: int, role: str, board_state: dict
) -> str | None:
    """Send COMMIT request; return h_commit or None on failure."""
    msg = ActionMessage(
        game_id=game_id,
        step=step,
        role="initiator",
        config_sha256=runner.config_sha256,
        timestamp=_now_iso(),
        phase="commit",
        board_state=board_state,
    )
    try:
        resp = await client.action(game_id, msg)
        h_commit = resp.get("h_commit")
        if not h_commit:
            logger.warning(f"[GameRunner] {role} commit returned no h_commit: {resp}")
            runner._log_event("commit_error", role, "commit", {"step": step, "error": str(resp)})
            return None
        runner._log_event(
            "commit_received", role, "commit", {"step": step, "h_commit": h_commit[:16] + "..."}
        )
        return h_commit
    except Exception as e:
        logger.error(f"[GameRunner] Commit request to {role} failed: {e}", exc_info=True)
        runner._log_event("commit_error", role, "commit", {"step": step, "error": str(e)})
        return None


async def request_reveal(
    runner: object, client: GameMCPClient, game_id: str, step: int, role: str
) -> dict | None:
    """Send REVEAL request; return reveal dict or None on failure."""
    msg = ActionMessage(
        game_id=game_id,
        step=step,
        role="initiator",
        config_sha256=runner.config_sha256,
        timestamp=_now_iso(),
        phase="reveal",
    )
    try:
        resp = await client.action(game_id, msg)
        move = resp.get("move")
        if not move:
            logger.warning(f"[GameRunner] {role} reveal returned no move: {resp}")
            runner._log_event("reveal_error", role, "reveal", {"step": step, "error": str(resp)})
            return None
        runner._log_event(
            "reveal_received",
            role,
            "reveal",
            {"step": step, "move": move, "h_commit": (resp.get("h_commit") or "")[:16]},
        )
        return resp
    except Exception as e:
        logger.error(f"[GameRunner] Reveal request to {role} failed: {e}", exc_info=True)
        runner._log_event("reveal_error", role, "reveal", {"step": step, "error": str(e)})
        return None


async def _run_single_turn(
    runner: object, game_id: str, step: int, board: object, rules: RulesEngine
) -> tuple[str | None, str | None] | None:
    """Run one commit-reveal turn. Returns (winner, abort_reason) or None on hard failure."""
    board_state_dict = {**runner._board_to_state(board), "scent_field": rules.get_scent_field()}
    cop_h = await request_commit(runner, runner.cop_client, game_id, step, "cop", board_state_dict)
    thief_h = await request_commit(
        runner, runner.thief_client, game_id, step, "thief", board_state_dict
    )
    if not cop_h or not thief_h:
        return None, f"Commit failed at step {step}"
    runner._cop_commits[step] = cop_h
    runner._thief_commits[step] = thief_h
    cop_rev = await request_reveal(runner, runner.cop_client, game_id, step, "cop")
    thief_rev = await request_reveal(runner, runner.thief_client, game_id, step, "thief")
    if not cop_rev or not thief_rev:
        return None, f"Reveal failed at step {step}"
    runner._cop_reveals[step] = cop_rev
    runner._thief_reveals[step] = thief_rev
    cop_move = _SHORT_TO_LONG.get(cop_rev.get("move", "STAY"), "STAY")
    thief_move = _SHORT_TO_LONG.get(thief_rev.get("move", "STAY"), "STAY")
    if not rules.validate_move("cop", cop_move):
        cop_move = "STAY"
    if not rules.validate_move("thief", thief_move):
        thief_move = "STAY"
    rules.apply_moves(cop_move, thief_move)
    runner._log_event(
        "move_applied",
        "initiator",
        "reveal",
        {
            "step": step,
            "cop_move": cop_move,
            "thief_move": thief_move,
            "cop_position": board.cop_position,
            "thief_position": board.thief_position,
        },
    )
    logger.info(
        f"[GameRunner] Step {step}: cop={cop_move} thief={thief_move} "
        f"cop_pos={board.cop_position} thief_pos={board.thief_position}"
    )
    outcome = rules.check_game_status()
    if outcome != GameOutcome.ONGOING:
        winner = "cop" if outcome == GameOutcome.COP_WIN else "thief"
        logger.info(f"[GameRunner] Game over at step {step}: {winner} wins")
        return winner, None
    return None, None


async def run_turn_loop(
    runner: object,
    game_id: str,
    board: object,
    rules: RulesEngine,
    max_turns: int,
    watchdog_timeout: float | None = None,
) -> tuple[str | None, str | None, int]:
    """Execute all game turns. Returns (winner, abort_reason, final_step)."""
    winner = abort_reason = None
    final_step = 0
    if watchdog_timeout is None:
        try:
            from agent.config.shared_config import load_shared_config

            watchdog_timeout = (
                load_shared_config().get("network_and_league", {}).get("watchdog_timeout_sec", 60)
            )
        except Exception:
            watchdog_timeout = 60
    try:
        for step in range(1, max_turns + 1):
            final_step = step
            try:
                outcome_tuple = await asyncio.wait_for(
                    _run_single_turn(runner, game_id, step, board, rules), timeout=watchdog_timeout
                )
            except TimeoutError:
                abort_reason = f"Watchdog timeout at step {step} (>{watchdog_timeout}s)"
                runner._log_event("abort", "initiator", "watchdog", {"reason": abort_reason})
                logger.warning(f"[GameRunner] {abort_reason}")
                winner = "TECHNICAL_LOSS"
                break
            if outcome_tuple is None:
                abort_reason = f"Turn {step} failed"
                runner._log_event("abort", "initiator", "turn", {"reason": abort_reason})
                break
            step_winner, step_abort = outcome_tuple
            if step_abort:
                abort_reason = step_abort
                break
            if step_winner:
                winner = step_winner
                break
    except Exception as e:
        logger.error(f"[GameRunner] Turn loop error: {e}", exc_info=True)
        abort_reason = str(e)
        winner = "TECHNICAL_LOSS"
    return winner, abort_reason, final_step
