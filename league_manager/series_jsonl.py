"""Append-only JSONL writer for league series events."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

VALID_EVENTS = {
    "series_created",
    "negotiation_locked",
    "gamelet_started",
    "gamelet_gameplay_terminal",
    "gamelet_audit_started",
    "gamelet_technical_loss",
    "gamelet_settled",
    "series_settled",
    "report_created",
    "report_sent",
}


class SeriesJSONL:
    """Append-only JSONL event log for one series.

    Every event includes full identity context (game_uid, game_id, timestamp).
    Never rewrites or truncates existing events.
    """

    def __init__(self, path: str | Path) -> None:
        """Initialise the JSONL writer at the given path.

        Args:
            path: File path for the JSONL log. Parent dirs are created.
        """
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(
        self,
        event: str,
        game_uid: str,
        game_id: str,
        sub_game_number: int | None = None,
        role: str | None = None,
        **extra: object,
    ) -> None:
        """Append one event line to the JSONL log.

        Args:
            event: Event name from VALID_EVENTS.
            game_uid: Canonical series identity.
            game_id: Protocol/course game ID.
            sub_game_number: Sub-game index (None for series-level events).
            role: Active role for this event (None for series-level events).
            **extra: Additional event-specific fields.

        Raises:
            ValueError: If event name is not in VALID_EVENTS.
        """
        if event not in VALID_EVENTS:
            raise ValueError(f"Unknown event: {event!r}")
        record = {
            "event": event,
            "game_uid": game_uid,
            "game_id": game_id,
            "sub_game_number": sub_game_number,
            "role": role,
            "timestamp": datetime.now(UTC).isoformat(),
            **extra,
        }
        line = json.dumps(record)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        logger.debug("JSONL event: %s sg=%s", event, sub_game_number)

    def read_all(self) -> list[dict]:
        """Read and parse all events from the JSONL file.

        Returns:
            List of event dicts in order of appending.
        """
        if not self._path.exists():
            return []
        lines = self._path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]
