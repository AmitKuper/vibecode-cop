"""Test that exactly 6 settled gamelets close the series."""

from league_manager.series_lifecycle import SeriesLifecycle


def test_six_sub_games_all_settled():
    """Series must close after exactly 6 gamelet_settled events."""
    sl = SeriesLifecycle(game_uid="six_rv_001", game_id="game_001")
    for i in range(1, 7):
        sl.on_event("gamelet_settled", {"sub_game_number": i})
    assert sl.settled_count == 6
    assert sl.is_closed is True


def test_five_sub_games_not_closed():
    """Series must NOT close after only 5 gamelet_settled events."""
    sl = SeriesLifecycle(game_uid="five_rv_001", game_id="game_001")
    for i in range(1, 6):
        sl.on_event("gamelet_settled", {"sub_game_number": i})
    assert sl.is_closed is False
