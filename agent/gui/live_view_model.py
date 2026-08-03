"""View model for the Live GUI — role-filtered, no hidden coordinates."""

import json
import threading
import time
from dataclasses import asdict, dataclass

from agent.observation import SafeLiveView


@dataclass
class LiveViewUpdate:
    """SSE event payload for the GUI."""

    view: SafeLiveView
    event_id: str
    timestamp_utc: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "event_id": self.event_id,
                "timestamp_utc": self.timestamp_utc,
                "view": asdict(self.view),
            }
        )


class LiveViewModel:
    """Thread-safe live view state. GUI reads from this; only Orchestrator writes."""

    def __init__(self, role: str, grid_size: int):
        self._role = role
        self._grid_size = grid_size
        self._current: SafeLiveView | None = None
        self._event_counter = 0
        self._lock = threading.Lock()

    def update(self, view: SafeLiveView) -> None:
        """Called by Orchestrator with a new SafeLiveView."""
        self._verify_no_hidden_coord(view)
        with self._lock:
            self._current = view
            self._event_counter += 1

    def _verify_no_hidden_coord(self, view: SafeLiveView) -> None:
        """Raise ValueError if hidden opponent coordinate is present."""
        view_dict = asdict(view)
        forbidden = [
            "opponent_position",
            "cop_position" if self._role == "thief" else "thief_position",
        ]
        for key in forbidden:
            if key in view_dict:
                raise ValueError(
                    f"Hidden coordinate {key!r} leaked into SafeLiveView for role {self._role!r}"
                )

    def get_current(self) -> SafeLiveView | None:
        with self._lock:
            return self._current

    def get_update(self) -> "LiveViewUpdate | None":
        with self._lock:
            if self._current is None:
                return None
            return LiveViewUpdate(
                view=self._current,
                event_id=str(self._event_counter),
                timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            )
