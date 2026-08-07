"""In-process six-gamelet series test — no network, no LLM."""

from cop_worker import mcp_server as ms
from league_manager.series_lifecycle import SeriesLifecycle

VALID_TERMS = {
    "board_size": 7,
    "smell_grid_size": 5,
    "decay_per_step": 0.1,
    "emit_intensity": 0.9,
    "max_steps": 35,
    "survival_threshold": 35,
    "barriers_max": 14,
    "num_games": 6,
}

ROLE_SCHEDULE = {1: "police", 2: "thief", 3: "police", 4: "thief", 5: "police", 6: "thief"}


def setup_function():
    """Clear registry before each test."""
    ms.clear_all_gamelets()


def test_six_gamelet_series_closes_lifecycle():
    """6 sequential start+shutdown cycles must close SeriesLifecycle."""
    sl = SeriesLifecycle(game_uid="six_proc_001", game_id="game_001")
    for sg in range(1, 7):
        role = ROLE_SCHEDULE[sg]
        ms.start_gamelet("six_proc_001", sg, VALID_TERMS, "local_thief", role)
        ms.shutdown_gamelet("six_proc_001", sg)
        sl.on_event("gamelet_settled", {"sub_game_number": sg, "winner": "police"})

    assert sl.is_closed is True
    assert sl.settled_count == 6


def test_series_result_is_not_none_after_six_settlements():
    """SeriesResult must be non-None after 6 settled gamelets."""
    sl = SeriesLifecycle(game_uid="six_proc_002", game_id="game_002")
    for sg in range(1, 7):
        sl.on_event("gamelet_settled", {"sub_game_number": sg, "winner": "police"})
    assert sl.result is not None


def test_shutdown_returns_dict_with_ok():
    """shutdown_gamelet must return a dict with 'ok' key."""
    ms.start_gamelet("six_proc_003", 1, VALID_TERMS, "peer", "police")
    result = ms.shutdown_gamelet("six_proc_003", 1)
    assert "ok" in result
    assert result["ok"] is True
