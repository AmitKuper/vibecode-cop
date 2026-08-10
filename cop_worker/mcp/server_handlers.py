"""Route handler functions for AgentMCPServer: start_game and action phases.

Every inbound MCP call passes through the ProtocolCoordinator before any game
logic executes.  An invalid protocol ordering is rejected with ok=False and
never reaches the handler callbacks or game log.

Transactional contract
----------------------
The SM is advanced BEFORE the callback runs.  If the callback raises, the SM is
rolled back to the pre-call state.  Permanent idempotency is only recorded after
a successful callback.
"""

from __future__ import annotations

import logging
from pathlib import Path

from cop_worker.crypto import verify_signature
from cop_worker.mcp.coordinator import (
    ProtocolCoordinator,
    gamelet_from_game_id,
    get_coordinator,
)
from cop_worker.mcp.log import GameLog
from cop_worker.mcp.messages import ActionMessage, validate_action_message
from cop_worker.mcp.server_common import _err
from cop_worker.mcp.server_notify import (  # noqa: F401  (public re-exports)
    notify_audit_begin,
    notify_commit_sent,
    notify_done,
    notify_reveal_sent,
    notify_step_begin,
    notify_technical_loss,
)
from cop_worker.mcp.server_phases_end import (
    _phase_abort,
    _phase_audit_summary,
    _phase_final_audit,
    _phase_game_end,
    _phase_result_agreement,
)
from cop_worker.mcp.server_phases_play import _phase_commit, _phase_reveal
from cop_worker.mcp.server_start import handle_start_game  # noqa: F401  (re-export)

logger = logging.getLogger(__name__)

# Keep the old helper for backwards compatibility; coordinator owns the canonical version.
_gamelet_from_game_id = gamelet_from_game_id

_PHASE_HANDLERS = {
    "commit": _phase_commit,
    "reveal": _phase_reveal,
    "final_audit": _phase_final_audit,
    "result_agreement": _phase_result_agreement,
    "audit_summary": _phase_audit_summary,
    "game_end": _phase_game_end,
    "abort": _phase_abort,
}


def handle_action(
    role: str,
    secret: str,
    config_sha256: str,
    games_dir: Path,
    game_logs: dict,
    handler_callbacks: dict,
    game_id: str,
    message_json: str,
    signature: str,
    coordinator: ProtocolCoordinator | None = None,
) -> dict:
    """Handle action — coordinator guards ordering, manages idempotency, rolls back on failure."""
    coord = coordinator or get_coordinator()
    gamelet = gamelet_from_game_id(game_id)
    game_log = game_logs.get(game_id)
    if not game_log:
        game_log = GameLog(game_id, games_dir)
        game_logs[game_id] = game_log

    try:
        msg = ActionMessage.from_json(message_json)
        base = {"game_id": game_id, "phase": msg.phase}

        if not verify_signature(msg.to_dict(), signature, secret):
            return _err(
                game_log,
                f"action:{msg.phase}",
                msg.role,
                msg.phase,
                "Signature verification failed",
                base,
            )

        if msg.config_sha256 != config_sha256:
            return _err(
                game_log,
                f"action:{msg.phase}",
                msg.role,
                msg.phase,
                f"Config mismatch: {msg.config_sha256} != {config_sha256}",
                base,
            )

        is_valid, error = validate_action_message(msg)
        if not is_valid:
            return _err(
                game_log,
                f"action:{msg.phase}",
                msg.role,
                msg.phase,
                error or "Invalid message",
                base,
            )

        # --- Route through coordinator for phase-specific guard + advance ---
        phase_handler = _PHASE_HANDLERS.get(msg.phase)
        if phase_handler is None:
            return _err(
                game_log,
                f"action:{msg.phase}",
                msg.role,
                msg.phase,
                f"Unknown phase: {msg.phase}",
                base,
            )
        return phase_handler(coord, game_log, handler_callbacks, game_id, gamelet, role, msg, base)

    except Exception as e:
        logger.error(f"Error in action: {e}", exc_info=True)
        game_log.append_error("action", "unknown", "unknown", str(e))
        return {"ok": False, "error": str(e), "game_id": game_id}
