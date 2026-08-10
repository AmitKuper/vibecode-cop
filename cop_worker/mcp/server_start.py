"""start_game handling: validate, register, and initialize the protocol SM."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from cop_worker.crypto import verify_signature
from cop_worker.mcp.coordinator import (
    ProtocolCoordinator,
    gamelet_from_game_id,
    get_coordinator,
)
from cop_worker.mcp.log import GameLog
from cop_worker.mcp.messages import StartGameMessage, validate_start_game_message
from cop_worker.mcp.protocol import ProtocolState
from cop_worker.mcp.server_common import _err

logger = logging.getLogger(__name__)


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
    base = {"game_id": "", "phase": "start_game"}
    try:
        untrusted = json.loads(message_json)
        if isinstance(untrusted, dict) and isinstance(untrusted.get("game_id"), str):
            base["game_id"] = untrusted["game_id"]
    except (json.JSONDecodeError, TypeError):
        pass
    try:
        msg = StartGameMessage.from_json(message_json)
        game_id = msg.game_id
        gamelet = gamelet_from_game_id(game_id)

        game_log = GameLog(game_id, games_dir)
        game_logs[game_id] = game_log
        actor = msg.roles.get(role, "unknown")
        base = {"game_id": game_id, "phase": "start_game"}

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

        if "on_start_game" in handler_callbacks:
            handler = handler_callbacks["on_start_game"]
            logger.info(f"Invoking on_start_game handler for {game_id}")
            result = handler(msg)
            if not isinstance(result, dict) or not result.get("ok"):
                return _err(
                    game_log,
                    "start_game",
                    actor,
                    "handshake",
                    f"Local Step-0 rejected peer: {result}",
                    base,
                )
            # A callback performs bilateral declaration verification.  Only a
            # successful callback may authorize READY.
            coord.on_handshake_complete(game_id, gamelet, role)
            game_log.append_message_received("start_game", role, "handshake", True)
            game_log.append("start_game", role, "handshake", "ok", result)
            return {**result, **base}

        coord.on_handshake_complete(game_id, gamelet, role)
        game_log.append_message_received("start_game", role, "handshake", True)
        return {"ok": True, "game_id": game_id, "role": role, "phase": "start_game"}

    except Exception as e:
        logger.error(f"Error in start_game: {e}", exc_info=True)
        if game_log:
            game_log.append_error("start_game", role, "handshake", str(e))
        return {"ok": False, "error": str(e), **base}
