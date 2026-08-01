"""Low-level helpers for the peer turn loop."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from agent.mcp.messages import ActionMessage

if TYPE_CHECKING:
    from agent.peer_runtime import PeerRuntime

logger = logging.getLogger(__name__)

_MOVE_ALIASES = {"N": "NORTH", "S": "SOUTH", "E": "EAST", "W": "WEST", "STAY": "STAY"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def send_commit(runtime: "PeerRuntime", step: int, h_commit: str) -> dict | None:
    """Send our COMMIT to opponent and return the response."""
    msg = ActionMessage(
        game_id=runtime.game_id, step=step, role=runtime.role,
        config_sha256=runtime.config_sha256, timestamp=_now(),
        phase="commit", h_commit=h_commit,
    )
    try:
        return await runtime.opponent_client.action(runtime.game_id, msg)
    except Exception as exc:
        logger.error(f"[PeerTurn] COMMIT send failed at step {step}: {exc}")
        return None


async def send_reveal(runtime: "PeerRuntime", step: int, reveal_payload: dict) -> dict | None:
    """Send our REVEAL — move/hint/intent/state_hash only; nonce withheld until final_audit."""
    msg = ActionMessage(
        game_id=runtime.game_id, step=step, role=runtime.role,
        config_sha256=runtime.config_sha256, timestamp=_now(),
        phase="reveal",
        move=reveal_payload["move"],
        hint=reveal_payload["hint"],
        intent=reveal_payload["intent"],
        state_hash=reveal_payload["state_hash"],
    )
    try:
        return await runtime.opponent_client.action(runtime.game_id, msg)
    except Exception as exc:
        logger.error(f"[PeerTurn] REVEAL send failed at step {step}: {exc}")
        return None


async def select_move(runtime: "PeerRuntime", board_state: dict) -> str:
    """Choose a move: RL policy → heuristic fallback.

    NOTE: LLM crew fallback is intentionally disabled for test runs.
    Re-enable _select_move_llm_async call here before submission.
    """
    obs = runtime._build_observation(board_state)
    try:
        move = runtime._select_move_rl(obs)
        if move:
            return move
    except Exception as exc:
        logger.warning(f"[PeerTurn] RL move selection failed: {exc}")
    from agent.board import Board
    moves = Board.from_dict(board_state).get_legal_moves(runtime.role)
    return moves[0] if moves else "STAY"


def build_board_state(runtime: "PeerRuntime") -> dict:
    """Snapshot current board as a plain dict for hashing."""
    b = runtime.board
    return {"cop_position": b.cop_position, "thief_position": b.thief_position, "turn": b.turn}


def get_watchdog_timeout() -> float:
    """Load watchdog timeout from shared config, defaulting to 60s."""
    try:
        from agent.config.shared_config import load_shared_config
        cfg = load_shared_config()
        return float(cfg.get("network_and_league", {}).get("watchdog_timeout_sec", 60))
    except Exception:
        return 60.0
