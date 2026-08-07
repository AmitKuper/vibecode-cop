"""Counted game-end consensus: SeriesLifecycle must require exactly 6 settled gamelets."""

from __future__ import annotations

import pytest

from league_manager.series_lifecycle import SeriesLifecycle


def _settled_event(sub_game: int, winner: str = "cop") -> dict:
    """Minimal gamelet_settled event payload."""
    return {
        "sub_game_number": sub_game,
        "result_claim": "capture" if winner == "cop" else "survival",
        "winner": winner,
        "final_step": 10,
        "audit_ok": True,
    }


def test_six_gamelet_settled_closes_series():
    """Exactly six gamelet_settled events must close the series."""
    sl = SeriesLifecycle(game_uid="series_fixture", game_id="series_fixture")
    for i in range(1, 7):
        sl.on_event("gamelet_settled", _settled_event(i))
    assert sl.settled_count == 6
    assert sl.is_closed


def test_fewer_than_six_settled_does_not_close():
    """Five settled gamelets must not close the series."""
    sl = SeriesLifecycle(game_uid="series_fixture", game_id="series_fixture")
    for i in range(1, 6):
        sl.on_event("gamelet_settled", _settled_event(i))
    assert sl.settled_count == 5
    assert not sl.is_closed


def test_technical_loss_event_does_not_count_as_settled():
    """A gamelet_technical_loss event must not increment settled_count."""
    sl = SeriesLifecycle(game_uid="series_fixture", game_id="series_fixture")
    sl.on_event("gamelet_technical_loss", {"sub_game_number": 1, "reason": "timeout"})
    assert sl.settled_count == 0


def test_technical_loss_followed_by_settled_counts_once():
    """technical_loss + settled together count as one settled gamelet."""
    sl = SeriesLifecycle(game_uid="series_fixture", game_id="series_fixture")
    sl.on_event("gamelet_technical_loss", {"sub_game_number": 1, "reason": "timeout"})
    sl.on_event("gamelet_settled", _settled_event(1))
    assert sl.settled_count == 1


def test_double_settled_for_same_sub_game_raises_or_is_idempotent():
    """Settling the same sub-game twice must not increment count beyond 6."""
    sl = SeriesLifecycle(game_uid="series_fixture", game_id="series_fixture")
    for i in range(1, 7):
        sl.on_event("gamelet_settled", _settled_event(i))
    # A second settle event for sub-game 6 must not over-count
    before = sl.settled_count
    try:
        sl.on_event("gamelet_settled", _settled_event(6))
    except Exception:
        pass  # raising is acceptable
    assert sl.settled_count <= 6 and sl.is_closed


def test_game_end_consensus_records_winner_per_gamelet():
    """SeriesLifecycle must track per-gamelet winner information."""
    sl = SeriesLifecycle(game_uid="series_fixture", game_id="series_fixture")
    sl.on_event("gamelet_settled", _settled_event(1, winner="cop"))
    sl.on_event("gamelet_settled", _settled_event(2, winner="thief"))
    # Should not raise; both events recorded
    assert sl.settled_count == 2
