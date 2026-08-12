"""Red/green tests for the 3-process counted composition architecture (LM variant, gamelet part).

New design: LeagueManager + CopWorker (mcp_server) + ThiefWorker.
Tests prove:
  - Gamelet construction in COUNTED mode
  - GameletError propagates through the series
  - Role is correctly threaded through the worker config
"""

from __future__ import annotations

import pytest

from tests.helpers_codex_counted_composition import _VALID_TERMS

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_complete_counted_gamelet_construction_passes_term_validation(tmp_path):
    """Gamelet can be constructed with a complete counted-mode terms dict."""
    from cop_worker.gamelet import Gamelet

    g = Gamelet(
        game_uid="series_fixture_g01",
        sub_game_number=1,
        terms=_VALID_TERMS,
        opponent_group="ABCD1234",
        role="police",
    )
    assert g.game_uid == "series_fixture_g01"
    assert g.sub_game_number == 1
    assert g.role == "police"


def test_start_gamelet_registers_gamelet_in_mcp_server():
    """start_gamelet must register the Gamelet under (game_uid, sub_game_number)."""
    import cop_worker.mcp_server as ms

    ms._GAMELETS.clear()
    result = ms.start_gamelet(
        game_uid="fixture_series_01",
        sub_game_number=1,
        terms=_VALID_TERMS,
        opponent_group="OPPONENTS",
        role="police",
    )
    assert result.get("ok") is True
    assert ("fixture_series_01", 1) in ms._GAMELETS
    ms._GAMELETS.clear()


def test_counted_gamelet_construction_failure_is_not_swallowed():
    """GameletError must propagate when terms are invalid."""
    from cop_worker.gamelet import Gamelet, GameletError

    bad_terms = {**_VALID_TERMS, "board_size": -1}
    with pytest.raises(GameletError, match="board_size"):
        Gamelet(
            game_uid="bad_series",
            sub_game_number=1,
            terms=bad_terms,
            opponent_group="OPPONENTS",
            role="police",
        )


def test_counted_series_propagates_gamelet_error():
    """GameletError from a gamelet must not be silently dropped."""
    import cop_worker.mcp_server as ms

    ms._GAMELETS.clear()
    # Duplicate registration must raise GameletError
    ms.start_gamelet("dup_series", 1, _VALID_TERMS, "OPP", "police")
    from cop_worker.gamelet import GameletError

    with pytest.raises(GameletError, match="already exists"):
        ms.start_gamelet("dup_series", 1, _VALID_TERMS, "OPP", "police")
    ms._GAMELETS.clear()


def test_counted_gamelet_role_is_threaded_from_config():
    """Gamelet must store the role exactly as supplied."""
    from cop_worker.gamelet import Gamelet

    for role in ("police", "thief"):
        g = Gamelet(
            game_uid="role_test",
            sub_game_number=1,
            terms=_VALID_TERMS,
            opponent_group="OPP",
            role=role,
        )
        assert g.role == role
