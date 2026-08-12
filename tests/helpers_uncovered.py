"""Shared helpers for the test_uncovered_* modules.

Split from test_uncovered_modules_coverage.py; no LLM, no network.
"""


def _make_report_context(game_dir, game_id="game_001", role="thief"):
    """Helper to build a minimal ReportContext for file report tests."""
    from league_manager.reports.base import ReportContext

    return ReportContext(
        game_id=game_id,
        role=role,
        group_id="group_01",
        opponent_group_id="group_02",
        game_dir=game_dir,
        game_state={
            "cop_position": [1, 1],
            "thief_position": [5, 5],
            "move_history": [
                {"cop": "N", "thief": "S"},
                {"cop": "E", "thief": "W"},
            ],
        },
        result={"winner": "thief"},
        start_timestamp="2026-01-01T00:00:00",
        end_timestamp="2026-01-01T00:05:00",
        config_hash="abc123",
        log_hash="def456",
        required_files={},
        optional_files={},
    )
