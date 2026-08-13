"""Process-wide LLM token ledger feeding the result artifacts.

Production hints are template-only (zero LLM tokens), so with the LLM disabled
every total here stays 0 and the emitted artifacts are byte-identical to the
old hardcoded zeros. When an LLM backend IS enabled, ``llm_hint`` records each
call's real usage counts here; league scoring reads the ledger for OUR side's
value (the opponent's spend is unknowable and stays 0).
"""

from __future__ import annotations

import threading


class TokenLedger:
    """Thread-safe token accumulator with gamelet and series scopes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._gamelet = 0
        self._series = 0
        self._history: list[int] = []

    def record(self, prompt_tokens: int, completion_tokens: int) -> None:
        """Add one LLM call's real usage counts to the open gamelet + series."""
        total = int(prompt_tokens) + int(completion_tokens)
        with self._lock:
            self._gamelet += total
            self._series += total

    def gamelet_total(self) -> int:
        """Total tokens recorded in the currently open gamelet."""
        with self._lock:
            return self._gamelet

    def series_total(self) -> int:
        """Total tokens recorded across the whole series (all gamelets)."""
        with self._lock:
            return self._series

    def reset_gamelet(self) -> int:
        """Close the open gamelet bucket: append it to history, zero it, return it."""
        with self._lock:
            closed = self._gamelet
            self._history.append(closed)
            self._gamelet = 0
            return closed

    def gamelet_history(self) -> list[int]:
        """Per-gamelet totals closed so far (one entry per reset_gamelet call)."""
        with self._lock:
            return list(self._history)

    def reset_series(self) -> None:
        """Zero everything (new series / test isolation)."""
        with self._lock:
            self._gamelet = 0
            self._series = 0
            self._history.clear()


#: The one process-wide ledger every recorder and reader shares.
_LEDGER = TokenLedger()


def record(prompt_tokens: int, completion_tokens: int) -> None:
    """Record one LLM call's real usage counts into the process ledger."""
    _LEDGER.record(prompt_tokens, completion_tokens)


def gamelet_total() -> int:
    """Tokens recorded in the currently open gamelet."""
    return _LEDGER.gamelet_total()


def series_total() -> int:
    """Tokens recorded across the whole series."""
    return _LEDGER.series_total()


def reset_gamelet() -> int:
    """Close the open gamelet bucket (returns its total)."""
    return _LEDGER.reset_gamelet()


def gamelet_history() -> list[int]:
    """Closed per-gamelet totals, in order."""
    return _LEDGER.gamelet_history()


def reset_series() -> None:
    """Zero the whole ledger."""
    _LEDGER.reset_series()
