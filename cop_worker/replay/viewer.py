"""ReplayViewer — lightweight step-by-step navigation for gamelet log JSON files."""

from __future__ import annotations

import json
from pathlib import Path


class ReplayViewerError(ValueError):
    """Raised on invalid log format."""


class ReplayViewer:
    """Loads a gamelet log JSON and enables step-by-step navigation."""

    def __init__(self, log_path: str | Path) -> None:
        """Load the gamelet log from log_path."""
        path = Path(log_path)
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ReplayViewerError(f"{log_path} must contain a JSON object")
        self._data = data
        self._steps: list[dict] = data.get("steps", [])
        self._index: int = 0

    def step_forward(self) -> dict | None:
        """Advance to the next step. Returns step record or None if at end."""
        if self._index < len(self._steps) - 1:
            self._index += 1
            return self._steps[self._index]
        return None

    def step_backward(self) -> dict | None:
        """Go back to the previous step. Returns step record or None if at start."""
        if self._index > 0:
            self._index -= 1
            return self._steps[self._index]
        return None

    def current_state(self) -> dict:
        """Return reconstructed game state at the current step."""
        if not self._steps:
            return {"game_uid": self._data.get("game_uid"), "step": 0, "record": None}
        record = self._steps[self._index]
        return {
            "game_uid": self._data.get("game_uid"),
            "sub_game_number": self._data.get("sub_game_number"),
            "role": self._data.get("role"),
            "step": record.get("step", self._index + 1),
            "record": record,
        }

    def is_at_start(self) -> bool:
        """Return True if at the first step."""
        return self._index == 0

    def is_at_end(self) -> bool:
        """Return True if at the last step."""
        return self._index >= len(self._steps) - 1
