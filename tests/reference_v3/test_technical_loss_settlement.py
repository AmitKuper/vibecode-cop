"""Test that technical loss produces gamelet_settled after proper sequence."""

from league_manager.series_lifecycle import SeriesLifecycle


def test_technical_loss_produces_gamelet_settled():
    """gamelet_technical_loss event must NOT settle; gamelet_settled must follow."""
    sl = SeriesLifecycle(game_uid="tl_rv_001", game_id="game_001")
    sl.on_event("gamelet_technical_loss", {"game_uid": "tl_rv_001", "sub_game_number": 1})
    assert sl.settled_count == 0
    sl.on_event("gamelet_settled", {"game_uid": "tl_rv_001", "sub_game_number": 1})
    assert sl.settled_count == 1
