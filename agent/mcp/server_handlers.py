"""Route handler functions for AgentMCPServer: start_game and action phases."""

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

logger = logging.getLogger(__name__)


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
    """Handle start_game call."""
    game_log = None
    try:
        msg = StartGameMessage.from_json(message_json)
        game_id = msg.game_id
        game_log = GameLog(game_id, games_dir)
        game_logs[game_id] = game_log
        actor = msg.roles.get(role, "unknown")
        base = {"game_id": game_id}

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
    """Handle action call - delegate to crewAI agents."""
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
