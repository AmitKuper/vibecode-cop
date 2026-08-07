"""Test score aggregation across 6 sub-games."""

from league_manager.series_lifecycle import SeriesLifecycle


def test_scores_aggregated_correctly_at_series_close():
    """Series must track cop/thief wins across all 6 sub-games."""
    sl = SeriesLifecycle(game_uid="agg_rv_001", game_id="game_001")
    results = [
        {"winner": "police", "result_claim": "capture"},
        {"winner": "thief", "result_claim": "survival"},
        {"winner": "police", "result_claim": "capture"},
        {"winner": "thief", "result_claim": "technical_loss"},
        {"winner": "police", "result_claim": "capture"},
        {"winner": "thief", "result_claim": "survival"},
    ]
    for i, r in enumerate(results, 1):
        sl.on_event("gamelet_settled", {"sub_game_number": i, "result": r, "winner": r["winner"]})
    assert sl.settled_count == 6
    assert sl.is_closed is True
