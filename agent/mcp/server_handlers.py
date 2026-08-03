"""Route handler functions for AgentMCPServer: start_game and action phases.

Every inbound MCP call passes through the SessionRegistry state machine
before any game logic executes.  An invalid protocol ordering is rejected
with ok=False and never reaches the handler callbacks or game log.
"""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path

from agent.mcp.crypto import verify_signature
from agent.mcp.log import GameLog
from agent.mcp.messages import (
    ActionMessage,
    StartGameMessage,
    validate_action_message,
    validate_start_game_message,
)
from agent.mcp.protocol import ProtocolState
from agent.mcp.session_registry import SessionEntry, get_registry

logger = logging.getLogger(__name__)

_registry = get_registry()


# Gamelet number is embedded in game_id as "<uuid>_g<N>" when present;
# fall back to 0 for bare game_ids (backwards compatibility).
def _gamelet_from_game_id(game_id: str) -> int:
    parts = game_id.rsplit("_g", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return int(parts[1])
    return 0


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
) -> dict:
    """Handle start_game call — transitions session to STEP0_NEGOTIATING."""
    game_log = None
    try:
        msg = StartGameMessage.from_json(message_json)
        game_id = msg.game_id
        gamelet = _gamelet_from_game_id(game_id)
        game_log = GameLog(game_id, games_dir)
        game_logs[game_id] = game_log
        actor = msg.roles.get(role, "unknown")
        base = {"game_id": game_id}

        # --- Protocol state guard ---
        entry: SessionEntry = _registry.get_or_create(game_id, gamelet, role)
        with entry.lock:
            ok, err = entry.sm.can_transition(ProtocolState.STEP0_NEGOTIATING)
            if not ok:
                return _err(
                    game_log,
                    "start_game",
                    actor,
                    "handshake",
                    f"Protocol violation: {err}",
                    base,
                )

            if not verify_signature(msg.to_dict(), signature, secret):
                return _err(
                    game_log,
                    "start_game",
                    actor,
                    "handshake",
                    "Signature verification failed",
                    base,
                )
            is_valid, error = validate_start_game_message(msg)
            if not is_valid:
                return _err(
                    game_log,
                    "start_game",
                    actor,
                    "handshake",
                    error or "Invalid message",
                    base,
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

            entry.sm.transition(ProtocolState.STEP0_NEGOTIATING)
            entry.sm.transition(ProtocolState.READY)

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
) -> dict:
    """Handle action call — state machine guards ordering before dispatch."""
    gamelet = _gamelet_from_game_id(game_id)
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

        # --- Protocol state guard (per-session lock held for entire check+mutate) ---
        entry: SessionEntry = _registry.get_or_create(game_id, gamelet, role)
        with entry.lock:
            state_err = _apply_inbound_phase(entry, msg)
            if state_err:
                return _err(
                    game_log,
                    f"action:{msg.phase}",
                    msg.role,
                    msg.phase,
                    f"Protocol violation: {state_err}",
                    base,
                )

        game_log.append_message_received("action", msg.role, msg.phase, True)

        if msg.phase == "commit":
            game_log.append_commit(msg.role, msg.step, msg.h_commit or "")
        elif msg.phase == "reveal":
            game_log.append_reveal(msg.role, msg.step, msg.move, msg.hint, msg.intent)
        elif msg.phase == "final_audit":
            game_log.append(
                "final_audit",
                msg.role,
                "final_audit",
                "ok",
                {"step": msg.step, "nonce_count": len(msg.nonces) if msg.nonces else 0},
            )

        if "on_action" in handler_callbacks:
            handler = handler_callbacks["on_action"]
            logger.info(f"Invoking on_action handler for {game_id} phase {msg.phase}")
            result = handler(game_id, msg)
            game_log.append(f"action:{msg.phase}", msg.role, msg.phase, "ok", result)
            return result

        return {"ok": True, "game_id": game_id, "phase": msg.phase, "step": msg.step}

    except Exception as e:
        logger.error(f"Error in action: {e}", exc_info=True)
        game_log.append_error("action", "unknown", "unknown", str(e))
        return {"ok": False, "error": str(e), "game_id": game_id}


def _apply_inbound_phase(entry: SessionEntry, msg: ActionMessage) -> str | None:
    """Apply an inbound phase message to the session state machine.

    Returns an error string if the transition is illegal, else None.
    Mutates entry.sm state on success.
    Caller must hold entry.lock.
    """
    phase = msg.phase
    sm = entry.sm

    if phase == "commit":
        ok, err = sm.guard_commit_received()
        if not ok:
            return err
        # Determine next state: if we already sent our commit → BOTH_COMMITTED
        next_state = (
            ProtocolState.BOTH_COMMITTED
            if sm.state == ProtocolState.COMMIT_SENT
            else ProtocolState.COMMIT_RECEIVED
        )
        sm.transition(next_state)

    elif phase == "reveal":
        ok, err = sm.guard_reveal_received()
        if not ok:
            return err
        next_state = (
            ProtocolState.STEP_VERIFIED
            if sm.state == ProtocolState.REVEAL_SENT
            else ProtocolState.REVEAL_RECEIVED
        )
        sm.transition(next_state)

    elif phase == "final_audit":
        ok, err = sm.guard_final_audit_received()
        if not ok:
            return err
        sm.transition(ProtocolState.RESULT_AGREEMENT)

    elif phase == "game_end":
        # game_end is informational — no state change required
        pass

    elif phase == "abort":
        with contextlib.suppress(ValueError):
            sm.transition(ProtocolState.ABORTED)

    return None


def notify_commit_sent(game_id: str, gamelet: int, role: str, step: int) -> None:
    """Called by the orchestrator after it sends its commit to the peer.

    Transitions the session from COMPUTING_MOVE or COMMIT_RECEIVED to the
    appropriate next state.
    """
    entry = _registry.get_or_create(game_id, gamelet, role)
    with entry.lock:
        sm = entry.sm
        if sm.state == ProtocolState.COMPUTING_MOVE:
            sm.transition(ProtocolState.COMMIT_SENT)
        elif sm.state == ProtocolState.COMMIT_RECEIVED:
            sm.transition(ProtocolState.BOTH_COMMITTED)
        entry.commit_sent_step = step


def notify_reveal_sent(game_id: str, gamelet: int, role: str, step: int) -> None:
    """Called by the orchestrator after it sends its reveal to the peer."""
    entry = _registry.get_or_create(game_id, gamelet, role)
    with entry.lock:
        sm = entry.sm
        if sm.state == ProtocolState.BOTH_COMMITTED:
            sm.transition(ProtocolState.REVEAL_SENT)
        elif sm.state == ProtocolState.REVEAL_RECEIVED:
            sm.transition(ProtocolState.STEP_VERIFIED)
        entry.reveal_sent_step = step


def notify_step_begin(game_id: str, gamelet: int, role: str) -> None:
    """Called at the start of each step to transition READY/STEP_VERIFIED → COMPUTING_MOVE."""
    entry = _registry.get_or_create(game_id, gamelet, role)
    with entry.lock:
        sm = entry.sm
        if sm.state in (ProtocolState.READY, ProtocolState.STEP_VERIFIED):
            sm.transition(ProtocolState.COMPUTING_MOVE)
            if sm.state == ProtocolState.COMPUTING_MOVE and sm.step > 0:
                sm.advance_step()


def notify_audit_begin(game_id: str, gamelet: int, role: str) -> None:
    """Transition STEP_VERIFIED → AUDITING."""
    entry = _registry.get_or_create(game_id, gamelet, role)
    with entry.lock:
        sm = entry.sm
        if sm.state == ProtocolState.STEP_VERIFIED:
            sm.transition(ProtocolState.AUDITING)


def notify_done(game_id: str, gamelet: int, role: str) -> None:
    """Transition REPORTING → DONE."""
    entry = _registry.get_or_create(game_id, gamelet, role)
    with entry.lock:
        sm = entry.sm
        if sm.state == ProtocolState.RESULT_AGREEMENT:
            sm.transition(ProtocolState.REPORTING)
        if sm.state == ProtocolState.REPORTING:
            sm.transition(ProtocolState.DONE)


def notify_technical_loss(game_id: str, gamelet: int, role: str) -> None:
    """Transition any non-terminal state → TECHNICAL_LOSS."""
    entry = _registry.get_or_create(game_id, gamelet, role)
    with entry.lock, contextlib.suppress(ValueError):
        entry.sm.transition(ProtocolState.TECHNICAL_LOSS)
