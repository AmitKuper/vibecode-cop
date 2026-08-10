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


from cop_worker.mcp.messages_validate import (  # noqa: E402,F401  (re-export)
    validate_action_message,
)
