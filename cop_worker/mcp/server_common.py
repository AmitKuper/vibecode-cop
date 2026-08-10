"""Shared helpers for the MCP action/start handlers."""

from __future__ import annotations

import logging

from cop_worker.mcp.log import GameLog
from cop_worker.mcp.messages import ActionMessage
from cop_worker.mcp.protocol import ProtocolState

logger = logging.getLogger(__name__)

# States that are valid for receiving a game_end message
_GAME_END_VALID_STATES = frozenset(
    {
        ProtocolState.STEP_VERIFIED,
        ProtocolState.AUDITING,
        ProtocolState.RESULT_AGREEMENT,
        # Also allow from any active play state (opponent may end game at any point)
        ProtocolState.COMPUTING_MOVE,
        ProtocolState.COMMIT_SENT,
        ProtocolState.COMMIT_RECEIVED,
        ProtocolState.BOTH_COMMITTED,
        ProtocolState.REVEAL_SENT,
        ProtocolState.REVEAL_RECEIVED,
        ProtocolState.READY,
    }
)


def _err(game_log: GameLog, tag: str, actor: str, phase: str, msg: str, extra: dict) -> dict:
    """Log an error and return a failure response dict."""
    game_log.append_error(tag, actor, phase, msg)
    return {"ok": False, "error": msg, **extra}


def _invoke_callback(handler_callbacks: dict, game_id: str, msg: ActionMessage) -> dict:
    """Invoke on_action callback if registered; return default ok response otherwise."""
    if "on_action" in handler_callbacks:
        handler = handler_callbacks["on_action"]
        try:
            result = handler(game_id, msg)
            payload = result if isinstance(result, dict) else {"ok": True}
            return {**payload, "game_id": game_id, "phase": msg.phase}
        except Exception as e:
            logger.error(f"on_action callback raised: {e}", exc_info=True)
            return {"ok": False, "error": str(e)}
    return {"ok": True, "game_id": game_id, "phase": msg.phase, "step": msg.step}
