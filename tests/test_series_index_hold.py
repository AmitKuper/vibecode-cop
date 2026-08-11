"""Index-hold rule: a window in which no game happened must NOT spend its index.

Live finding (uoh-sqak friendlies #2/#3, 2026-08-12 00:01 and 00:15): our series
loop spent an index on every failed window while their peer held-and-converged,
so after one mid-series failure the two counters could never meet again. The fix
classifies failures at the source: discovery / handshake / zero-turn timeouts
raise ``NoGameHappenedError`` (retriable at the same index, bounded by wall-clock);
a timeout AFTER opponent steps were exchanged stays a plain ``TimeoutError``
(the index is spent — replaying a partially played game would corrupt audits).
"""

from __future__ import annotations

import asyncio
import sys
from collections import deque
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from live_match_ref3 import NoGameHappenedError, _poll_agreement, _poll_turn  # noqa: E402


class _Inbox:
    def __init__(self, played=(), buffered=()):
        self.played = set(played)
        self.buffered = set(buffered)
        self.next_step = (max(self.played) + 1) if self.played else 1

    def turn_for(self, step):
        return {"step": step}


def test_no_game_happened_is_a_timeout_error() -> None:
    # Existing except-TimeoutError sites keep catching it unchanged.
    assert issubclass(NoGameHappenedError, TimeoutError)


def test_handshake_greeting_timeout_is_retriable() -> None:
    with pytest.raises(NoGameHappenedError):
        asyncio.run(_poll_agreement(deque(), 3, timeout=0.1))


def test_zero_turn_window_is_retriable() -> None:
    # Their peer handshook and then never played a single step (the observed
    # silent-peer mode): no game happened, the index must be held.
    with pytest.raises(NoGameHappenedError):
        asyncio.run(_poll_turn(_Inbox(), 1, timeout=0.1))


def test_timeout_after_steps_exchanged_spends_the_index() -> None:
    # Steps 1-2 arrived, step 3 never did: a game genuinely started and died.
    inbox = _Inbox(played=(1, 2))
    with pytest.raises(TimeoutError) as exc_info:
        asyncio.run(_poll_turn(inbox, 3, timeout=0.1))
    assert not isinstance(exc_info.value, NoGameHappenedError)
    assert "steps played=[1, 2]" in str(exc_info.value)
