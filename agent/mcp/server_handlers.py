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

from agent.mcp.coordinator import ProtocolCoordinator, gamelet_from_game_id, get_coordinator
from agent.mcp.crypto import verify_signature
from agent.mcp.log import GameLog
from agent.mcp.messages import (
    ActionMessage,
    StartGameMessage,
    validate_action_message,
    validate_start_game_message,
)
from agent.mcp.protocol import ProtocolState

logger = logging.getLogger(__name__)

# Keep the old helper for backwards compatibility; coordinator now owns the canonical version.
_gamelet_from_game_id = gamelet_from_game_id

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


def handle_start_game(
    role: str,
    secret: str,
    config_sha256: str,
    games_dir: Path,
    game_logs: dict,
    handler_callbacks: dict,
    message_json: str,
    signature: str,
    coordinator: ProtocolCoordinator | None = None,
) -> dict:
    """Handle start_game — validate then transition session to READY via coordinator.

    Idempotent: a second start_game for a session already in READY returns ok=True.
    """
    coord = coordinator or get_coordinator()
    game_log = None
    try:
        msg = StartGameMessage.from_json(message_json)
        game_id = msg.game_id
        gamelet = gamelet_from_game_id(game_id)

        game_log = GameLog(game_id, games_dir)
        game_logs[game_id] = game_log
        actor = msg.roles.get(role, "unknown")
        base = {"game_id": game_id}

        # Guard: only accept start_game when SM is in IDLE or READY (idempotent)
        current_state = coord.get_state(game_id, gamelet, role)
        if current_state is not None and current_state not in (
            ProtocolState.IDLE,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
        ):
            return _err(
                game_log,
                "start_game",
                actor,
                "handshake",
                f"Protocol violation: start_game received in state {current_state.value}",
                base,
            )

        if not verify_signature(msg.to_dict(), signature, secret):
            return _err(
                game_log, "start_game", actor, "handshake", "Signature verification failed", base
            )

        is_valid, error = validate_start_game_message(msg)
        if not is_valid:
            return _err(
                game_log, "start_game", actor, "handshake", error or "Invalid message", base
            )

        if msg.config_sha256 != config_sha256:
            return _err(
                game_log,
                "start_game",
                actor,
                "handshake",
                f"Config mismatch: {msg.config_sha256} != {config_sha256}",
                base,
            )

        if msg.protocol_version != "1.0":
            return _err(
                game_log,
                "start_game",
                actor,
                "handshake",
                f"Protocol version mismatch: {msg.protocol_version}",
                base,
            )

        if role not in msg.roles:
            return _err(
                game_log,
                "start_game",
                "unknown",
                "handshake",
                f"My role '{role}' not in agreed roles",
                base,
            )

        # Advance SM to READY (idempotent if already READY)
        coord.on_handshake_complete(game_id, gamelet, role)

        game_log.append_message_received("start_game", role, "handshake", True)

        if "on_start_game" in handler_callbacks:
            handler = handler_callbacks["on_start_game"]
            logger.info(f"Invoking on_start_game handler for {game_id}")
            result = handler(msg)
            game_log.append("start_game", role, "handshake", "ok", result)
            return result

        return {"ok": True, "game_id": game_id, "role": role}

    except Exception as e:
        logger.error(f"Error in start_game: {e}", exc_info=True)
        if game_log:
            game_log.append_error("start_game", role, "handshake", str(e))
        return {"ok": False, "error": str(e)}


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
        if msg.phase == "commit":
            h_commit = msg.h_commit or ""
            ok, err, cached, prev_state = coord.check_and_advance_inbound_commit(
                game_id, gamelet, role, msg.step, h_commit
            )
            if not ok:
                return _err(
                    game_log,
                    "action:commit",
                    msg.role,
                    "commit",
                    f"Protocol violation: {err}",
                    base,
                )
            if cached is not None:
                return cached  # Exact duplicate — return cached response

            game_log.append_commit(msg.role, msg.step, h_commit)

            result = _invoke_callback(handler_callbacks, game_id, msg)
            if result.get("ok"):
                coord.record_commit_response(game_id, gamelet, role, msg.step, h_commit, result)
                # If passive side returned h_commit, advance COMMIT_RECEIVED → BOTH_COMMITTED
                if result.get("h_commit"):
                    coord.on_passive_commit_sent(
                        game_id, gamelet, role, msg.step, result["h_commit"]
                    )
            else:
                # Callback failed — rollback SM
                if prev_state is not None:
                    coord.rollback_inbound_commit(game_id, gamelet, role, prev_state)
            return result

        elif msg.phase == "reveal":
            move = msg.move or ""
            hint = msg.hint
            intent = msg.intent
            state_hash = msg.state_hash
            ok, err, cached, prev_state = coord.check_and_advance_inbound_reveal(
                game_id,
                gamelet,
                role,
                msg.step,
                move,
                hint=hint,
                intent=intent,
                state_hash=state_hash,
            )
            if not ok:
                return _err(
                    game_log,
                    "action:reveal",
                    msg.role,
                    "reveal",
                    f"Protocol violation: {err}",
                    base,
                )
            if cached is not None:
                return cached

            game_log.append_reveal(msg.role, msg.step, msg.move, msg.hint, msg.intent)

            result = _invoke_callback(handler_callbacks, game_id, msg)
            if result.get("ok"):
                coord.record_reveal_response(
                    game_id,
                    gamelet,
                    role,
                    msg.step,
                    move,
                    result,
                    hint=hint,
                    intent=intent,
                    state_hash=state_hash,
                )
                # If passive side returned move, advance REVEAL_RECEIVED → STEP_VERIFIED
                if result.get("move"):
                    coord.on_passive_reveal_sent(game_id, gamelet, role, msg.step, result["move"])
            else:
                if prev_state is not None:
                    coord.rollback_inbound_reveal(game_id, gamelet, role, prev_state)
            return result

        elif msg.phase == "final_audit":
            ok, err, prev_state = coord.check_final_audit_guard(game_id, gamelet, role)
            if not ok:
                return _err(
                    game_log,
                    "action:final_audit",
                    msg.role,
                    "final_audit",
                    f"Protocol violation: {err}",
                    base,
                )
            game_log.append(
                "final_audit",
                msg.role,
                "final_audit",
                "ok",
                {"step": msg.step, "nonce_count": len(msg.nonces) if msg.nonces else 0},
            )
            result = _invoke_callback(handler_callbacks, game_id, msg)
            return result

        elif msg.phase == "game_end":
            # Fix 7: Coordinator guard for game_end — only accept in active/audit states
            current_state = coord.get_state(game_id, gamelet, role)
            if current_state is not None and current_state not in _GAME_END_VALID_STATES:
                return _err(
                    game_log,
                    "action:game_end",
                    msg.role,
                    "game_end",
                    f"Protocol violation: game_end received in state {current_state.value}",
                    base,
                )
            game_log.append(
                "game_end",
                msg.role,
                "game_end",
                "ok",
                {"step": msg.step, "reason": msg.reason},
            )
            result = _invoke_callback(handler_callbacks, game_id, msg)
            return result

        elif msg.phase == "abort":
            # Fix 7: Route abort through coordinator for proper logging and state tracking
            coord.on_technical_loss(
                game_id,
                gamelet,
                role,
                reason=f"abort received from {msg.role}",
            )
            game_log.append(
                "abort",
                msg.role,
                "abort",
                "ok",
                {"step": msg.step, "reason": getattr(msg, "reason", "")},
            )
            result = _invoke_callback(handler_callbacks, game_id, msg)
            return result

        else:
            return _err(
                game_log,
                f"action:{msg.phase}",
                msg.role,
                msg.phase,
                f"Unknown phase: {msg.phase}",
                base,
            )

    except Exception as e:
        logger.error(f"Error in action: {e}", exc_info=True)
        game_log.append_error("action", "unknown", "unknown", str(e))
        return {"ok": False, "error": str(e), "game_id": game_id}


def _invoke_callback(handler_callbacks: dict, game_id: str, msg: ActionMessage) -> dict:
    """Invoke on_action callback if registered; return default ok response otherwise."""
    if "on_action" in handler_callbacks:
        handler = handler_callbacks["on_action"]
        try:
            result = handler(game_id, msg)
            return result if isinstance(result, dict) else {"ok": True}
        except Exception as e:
            logger.error(f"on_action callback raised: {e}", exc_info=True)
            return {"ok": False, "error": str(e)}
    return {"ok": True, "game_id": game_id, "phase": msg.phase, "step": msg.step}


# ---------------------------------------------------------------------------
# Outbound notify helpers — thin wrappers around coordinator for callers
# that hold a game_id/gamelet/role tuple.
# ---------------------------------------------------------------------------


def notify_commit_sent(game_id: str, gamelet: int, role: str, step: int) -> None:
    """Called by the orchestrator after it sends its commit to the peer."""
    get_coordinator().on_commit_exchange_complete(game_id, gamelet, role, step)


def notify_reveal_sent(game_id: str, gamelet: int, role: str, step: int) -> None:
    """Called by the orchestrator after it sends its reveal to the peer."""
    get_coordinator().on_reveal_exchange_complete(game_id, gamelet, role, step)


def notify_step_begin(game_id: str, gamelet: int, role: str, step: int = 0) -> None:
    """Called at the start of each step — READY/STEP_VERIFIED → COMPUTING_MOVE."""
    get_coordinator().begin_step(game_id, gamelet, role, step)


def notify_audit_begin(game_id: str, gamelet: int, role: str) -> None:
    """Advance STEP_VERIFIED → AUDITING."""
    get_coordinator().on_audit_begin(game_id, gamelet, role)


def notify_done(game_id: str, gamelet: int, role: str) -> None:
    """Advance → DONE."""
    get_coordinator().on_done(game_id, gamelet, role)


def notify_technical_loss(game_id: str, gamelet: int, role: str, reason: str = "") -> None:
    """Transition any non-terminal → TECHNICAL_LOSS."""
    get_coordinator().on_technical_loss(game_id, gamelet, role, reason=reason)
