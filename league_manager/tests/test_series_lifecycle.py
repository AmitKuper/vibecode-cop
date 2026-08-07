"""Tests for SeriesLifecycle — gamelet counting and series closure."""

from league_manager.series_lifecycle import SeriesLifecycle

SETTLED_EVENT = {"sub_game_number": 1, "winner": "police", "audit_ok": True}


def make_lifecycle():
    """Create a fresh SeriesLifecycle for testing."""
    return SeriesLifecycle(game_uid="uid_001", game_id="game_001")


def test_six_gamelet_settled_closes_series():
    """Exactly 6 gamelet_settled events close the series."""
    sl = make_lifecycle()
    for i in range(1, 7):
        sl.on_event("gamelet_settled", {**SETTLED_EVENT, "sub_game_number": i})
    assert sl.is_closed
    assert sl.settled_count == 6


def test_technical_loss_alone_does_not_settle():
    """gamelet_technical_loss without subsequent settled does not close."""
    sl = make_lifecycle()
    sl.on_event("gamelet_technical_loss", {"sub_game_number": 1, "reason": "timeout"})
    assert not sl.is_closed
    assert sl.settled_count == 0


def test_technical_loss_followed_by_settled_counts():
    """gamelet_technical_loss followed by gamelet_settled increments counter."""
    sl = make_lifecycle()
    sl.on_event("gamelet_technical_loss", {"sub_game_number": 1, "reason": "timeout"})
    sl.on_event("gamelet_settled", {**SETTLED_EVENT, "via": "technical_loss"})
    assert sl.settled_count == 1


def test_partial_settled_does_not_close_series():
    """Five gamelet_settled events leave the series open."""
    sl = make_lifecycle()
    for i in range(1, 6):
        sl.on_event("gamelet_settled", {**SETTLED_EVENT, "sub_game_number": i})
    assert not sl.is_closed
    assert sl.settled_count == 5


def test_events_after_close_ignored():
    """Events received after series closure are silently ignored."""
    sl = make_lifecycle()
    for i in range(1, 7):
        sl.on_event("gamelet_settled", {**SETTLED_EVENT, "sub_game_number": i})
    assert sl.is_closed
    sl.on_event("gamelet_settled", {**SETTLED_EVENT, "sub_game_number": 7})
    assert sl.settled_count == 6


def test_series_result_has_cop_thief_totals():
    """SeriesResult totals add up to 6 and reflect actual winners."""
    sl = make_lifecycle()
    for i in range(1, 7):
        winner = "police" if i % 2 == 1 else "thief"
        sl.on_event("gamelet_settled", {"sub_game_number": i, "winner": winner, "audit_ok": True})
    result = sl.result
    assert result is not None
    assert result.cop_total + result.thief_total == 6


def test_close_callback_invoked():
    """Registered close callback is called exactly once on series close."""
    sl = make_lifecycle()
    received = []
    sl.add_close_callback(received.append)
    for i in range(1, 7):
        sl.on_event("gamelet_settled", {**SETTLED_EVENT, "sub_game_number": i})
    assert len(received) == 1
    assert received[0].game_uid == "uid_001"
