"""Append-only game log for MCP protocol messages."""

import json
import logging
from datetime import datetime
from pathlib import Path

from agent.mcp.log_replay import load_from_file

logger = logging.getLogger(__name__)

# Re-export for backwards compatibility
__all__ = ["GameLog", "load_from_file"]


class GameLog:
    """Append-only JSONL log of all game events."""

    def __init__(self, game_id: str, log_dir: Path):
        """Initialize game log."""
        self.game_id = game_id
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / f"{game_id}.jsonl"
        self.events: list[dict] = []

    def append(
        self,
        event_type: str,
        role: str,
        phase: str,
        status: str,  # "ok", "error", "warning"
        details: dict,
        error: str | None = None,
    ) -> None:
        """Append an event to the log and persist it."""
        event = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_type": event_type,
            "role": role,
            "phase": phase,
            "status": status,
            "details": details,
        }
        if error:
            event["error"] = error
        self.events.append(event)
        self._write_to_file(event)
        log_level = logging.ERROR if status == "error" else logging.INFO
        logger.log(
            log_level,
            f"Game {self.game_id}: {event_type} ({phase}) - {status}",
            extra={"details": details},
        )

    def append_message_received(
        self,
        message_type: str,
        role: str,
        phase: str,
        is_valid: bool,
        error: str | None = None,
    ) -> None:
        """Log a received message."""
        self.append(
            event_type=f"message_received:{message_type}",
            role=role,
            phase=phase,
            status="ok" if is_valid else "error",
            details={"valid": is_valid},
            error=error,
        )

    def append_message_sent(self, message_type: str, role: str, phase: str) -> None:
        """Log a sent message."""
        self.append(
            event_type=f"message_sent:{message_type}",
            role=role,
            phase=phase,
            status="ok",
            details={"sent": True},
        )

    def append_commit(self, role: str, step: int, h_commit: str) -> None:
        """Log a commit phase."""
        preview = (h_commit[:16] + "...") if h_commit else "(request)"
        self.append(
            event_type="commit",
            role=role,
            phase="commit",
            status="ok",
            details={"step": step, "h_commit": preview},
        )

    def append_reveal(
        self,
        role: str,
        step: int,
        move: str,
        hint: str | None = None,
        intent: str | None = None,
    ) -> None:
        """Log a reveal phase."""
        self.append(
            event_type="reveal",
            role=role,
            phase="reveal",
            status="ok",
            details={"step": step, "move": move, "hint": hint is not None, "intent": intent},
        )

    def append_commitment_verified(self, role: str, step: int, is_valid: bool) -> None:
        """Log commitment verification result."""
        self.append(
            event_type="commitment_verified",
            role=role,
            phase="final_audit",
            status="ok" if is_valid else "error",
            details={"step": step, "verified": is_valid},
            error=None if is_valid else "Commitment verification failed",
        )

    def append_error(
        self,
        event_type: str,
        role: str,
        phase: str,
        error_msg: str,
        details: dict | None = None,
    ) -> None:
        """Log an error event."""
        self.append(
            event_type=event_type,
            role=role,
            phase=phase,
            status="error",
            details=details or {},
            error=error_msg,
        )

    def get_all_events(self) -> list[dict]:
        """Get all logged events."""
        return self.events.copy()

    def get_events_by_phase(self, phase: str) -> list[dict]:
        """Get events for a specific phase."""
        return [e for e in self.events if e["phase"] == phase]

    def _write_to_file(self, event: dict) -> None:
        """Append event to JSONL file."""
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, separators=(",", ":")) + "\n")
        except OSError as e:
            logger.error(f"Failed to write to game log: {e}")
