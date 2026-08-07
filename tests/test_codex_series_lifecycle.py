"""Tests for SeriesLifecycle — series closure and event counting."""

from league_manager.series_lifecycle import SeriesLifecycle

SETTLED_EVENT = {"sub_game_number": 1, "winner": "police", "audit_ok": True}


def make_lifecycle(uid="uid_test_001", gid="game_001"):
    """Create a fresh SeriesLifecycle."""
    return SeriesLifecycle(game_uid=uid, game_id=gid)


def test_six_settled_closes_series():
    """Exactly 6 gamelet_settled events must close the series."""
    sl = make_lifecycle()
    for i in range(1, 7):
        sl.on_event("gamelet_settled", {**SETTLED_EVENT, "sub_game_number": i})
    assert sl.is_closed is True
    assert sl.settled_count == 6


def test_five_settled_leaves_series_open():
    """Five gamelet_settled events must not close the series."""
    sl = make_lifecycle()
    for i in range(1, 6):
        sl.on_event("gamelet_settled", {**SETTLED_EVENT, "sub_game_number": i})
    assert sl.is_closed is False


def test_events_after_close_are_ignored():
    """Events after closure must be silently ignored."""
    sl = make_lifecycle()
    for i in range(1, 7):
        sl.on_event("gamelet_settled", {**SETTLED_EVENT, "sub_game_number": i})
    sl.on_event("gamelet_settled", {**SETTLED_EVENT, "sub_game_number": 7})
    assert sl.settled_count == 6


def test_technical_loss_alone_does_not_settle():
    """gamelet_technical_loss alone must not increment settled_count."""
    sl = make_lifecycle()
    sl.on_event("gamelet_technical_loss", {"sub_game_number": 1, "reason": "timeout"})
    assert sl.settled_count == 0
    assert sl.is_closed is False


def test_result_has_cop_thief_totals_after_close():
    """SeriesResult must have cop_total and thief_total summing to 6."""
    sl = make_lifecycle()
    for i in range(1, 7):
        winner = "police" if i <= 3 else "thief"
        sl.on_event("gamelet_settled", {"sub_game_number": i, "winner": winner, "audit_ok": True})
    result = sl.result
    assert result is not None
    assert result.cop_total + result.thief_total == 6


def test_close_callback_invoked_once():
    """Close callback must be invoked exactly once on series closure."""
    sl = make_lifecycle()
    received = []
    sl.add_close_callback(received.append)
    for i in range(1, 7):
        sl.on_event("gamelet_settled", {**SETTLED_EVENT, "sub_game_number": i})
    assert len(received) == 1
