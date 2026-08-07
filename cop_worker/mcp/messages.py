"""Message schemas and validation for MCP protocol.

Base enums and validators live here. Game-specific dataclasses
(StartGameMessage, ActionMessage) live in messages_game.py and are
re-exported from this module for backwards compatibility.
"""

import logging
from enum import Enum

from cop_worker.mcp.messages_game import ActionMessage, StartGameMessage

logger = logging.getLogger(__name__)

# Re-export so all existing ``from cop_worker.mcp.messages import …`` still work.
__all__ = [
    "MessagePhase",
    "MessageType",
    "StartGameMessage",
    "ActionMessage",
    "validate_start_game_message",
    "validate_action_message",
]


class MessagePhase(Enum):
    """Protocol phases for action messages."""

    COMMIT = "commit"
    ACK = "ack"
    REVEAL = "reveal"
    FINAL_AUDIT = "final_audit"
    AUDIT_SUMMARY = "audit_summary"
    ABORT = "abort"
    GAME_END = "game_end"
    RESULT_AGREEMENT = "result_agreement"


class MessageType(Enum):
    """Message types for action."""

    MOVE = "move"
    ACK = "ack"
    ABORT = "abort"


def validate_start_game_message(msg: StartGameMessage) -> tuple[bool, str | None]:
    """Validate StartGameMessage.

    Args:
        msg: Message to validate.

    Returns:
        (is_valid, error_message)
    """
    if not msg.game_id:
        return False, "game_id is required"

    if not msg.roles or "cop" not in msg.roles or "police" not in msg.roles:
        return False, "roles must contain both 'cop' and 'police'"

    if not msg.config_sha256 or len(msg.config_sha256) != 64:
        return False, "config_sha256 must be 64-char hex (SHA-256)"

    if msg.protocol_version != "1.0":
        return False, f"protocol_version must be '1.0', got {msg.protocol_version}"

    if not msg.endpoint or not msg.endpoint.startswith("http"):
        return False, "endpoint must be a valid URL"

    if not msg.timestamp:
        return False, "timestamp is required"

    return True, None


def validate_action_message(msg: ActionMessage) -> tuple[bool, str | None]:
    """Validate ActionMessage.

    Args:
        msg: Message to validate.

    Returns:
        (is_valid, error_message)
    """
    if not msg.game_id:
        return False, "game_id is required"

    if msg.step < 0:
        return False, f"step must be >= 0, got {msg.step}"

    if msg.role not in ["cop", "police", "initiator"]:
        return False, f"role must be 'cop', 'police', or 'initiator', got {msg.role}"

    if not msg.config_sha256 or len(msg.config_sha256) != 64:
        return False, "config_sha256 must be 64-char hex (SHA-256)"

    if not msg.timestamp:
        return False, "timestamp is required"

    # Validate phase-specific fields
    try:
        phase = MessagePhase(msg.phase)
    except ValueError:
        return False, f"phase must be one of {[p.value for p in MessagePhase]}, got {msg.phase}"

    if phase == MessagePhase.COMMIT:
        # h_commit is optional in COMMIT requests (GameRunner asks agent to generate one).
        # When h_commit IS present it must be valid hex.
        if msg.h_commit is not None and len(msg.h_commit) != 64:
            return False, "COMMIT phase h_commit must be 64-char hex when provided"

    elif phase == MessagePhase.ACK:
        if not msg.h_commit_ack:
            return False, "ACK phase requires h_commit_ack"

    elif phase == MessagePhase.REVEAL:
        # REVEAL is also used as a request (GameRunner -> Agent); move/state_hash only
        # required when an agent is SENDING a reveal, not when receiving the request.
        # PLACE_* moves encode cop barrier placement (e.g. PLACE_N = barrier north of cop).
        _valid_moves = {
            "N",
            "S",
            "E",
            "W",
            "STAY",
            "NORTH",
            "SOUTH",
            "EAST",
            "WEST",
            "PLACE_N",
            "PLACE_S",
            "PLACE_E",
            "PLACE_W",
        }
        if msg.move is not None and msg.move not in _valid_moves:
            return False, f"REVEAL phase move must be a valid direction or PLACE_*, got {msg.move}"
        if msg.intent is not None and msg.intent not in ["truth", "lie", "ambiguous", "bluff"]:
            return False, f"intent must be truth/lie/ambiguous/bluff, got {msg.intent}"
        if msg.hint is not None and len(msg.hint.split()) > 15:
            return False, f"hint exceeds 15 words ({len(msg.hint.split())})"
        if msg.state_hash is not None and len(msg.state_hash) != 64:
            return False, "state_hash must be 64-char hex when provided"

    elif phase == MessagePhase.FINAL_AUDIT:
        # nonces dict is optional in requests (GameRunner sends empty dict to request nonces).
        if msg.nonces is not None and not isinstance(msg.nonces, dict):
            return False, "FINAL_AUDIT nonces must be a dict when provided"
        # game_log is always optional

    elif phase == MessagePhase.AUDIT_SUMMARY and not msg.signed_audit_summary:
        return False, "AUDIT_SUMMARY phase requires signed_audit_summary"

    elif phase == MessagePhase.ABORT and not msg.reason:
        return False, "ABORT phase requires reason"

    elif phase == MessagePhase.GAME_END and not msg.reason:
        return False, "GAME_END phase requires reason"

    # All phases validated above

    return True, None
