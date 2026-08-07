"""Anomaly detection for Gmail send bursts."""

import threading
import time
from collections import deque


class DosDetector:
    """Detect burst/loop/repeated game_id anomalies."""

    def __init__(self, max_per_minute: int = 10, window_s: float = 60.0, max_per_game: int = 2):
        self._max_per_minute = max_per_minute
        self._window_s = window_s
        self._max_per_game = max_per_game
        self._timestamps: deque = deque()
        self._game_counts: dict = {}
        self._lock = threading.Lock()
        self._locked = False

    def check(self, game_id: str) -> tuple[bool, str]:
        """Returns (allowed, reason). Sets locked=True on anomaly."""
        with self._lock:
            if self._locked:
                return False, "DOS lock active"
            now = time.monotonic()
            # Prune old timestamps
            while self._timestamps and now - self._timestamps[0] > self._window_s:
                self._timestamps.popleft()
            if len(self._timestamps) >= self._max_per_minute:
                self._locked = True
                return False, f"Burst detected: {len(self._timestamps)} sends in {self._window_s}s"
            # Check per-game limit
            count = self._game_counts.get(game_id, 0)
            if count >= self._max_per_game:
                self._locked = True
                return False, f"Repeated game_id {game_id!r}: count={count}"
            self._timestamps.append(now)
            self._game_counts[game_id] = count + 1
            return True, ""

    def reset_lock(self) -> None:
        with self._lock:
            self._locked = False

    @property
    def is_locked(self) -> bool:
        return self._locked
