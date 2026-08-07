"""Tests for LeagueManager Router — routing table and error handling."""

import pytest

from league_manager.router import Router, RouterError
from league_manager.tests.mock_worker import MockWorker


def make_router():
    """Create a Router with mock workers and a registered series."""
    cop = MockWorker(role="police")
    thief = MockWorker(role="thief")
    r = Router(cop_worker=cop, thief_worker=thief)
    r.register_series(game_uid="uid_codex_001", starting_role="police")
    return r, cop, thief


def test_router_routes_sg1_to_cop():
    """Sub-game 1 must route to cop worker."""
    r, cop, thief = make_router()
    r.route("uid_codex_001", 1, "get_status", {})
    cop.assert_called("get_status")


def test_router_routes_sg2_to_thief():
    """Sub-game 2 must route to thief worker."""
    r, cop, thief = make_router()
    r.route("uid_codex_001", 2, "get_status", {})
    thief.assert_called("get_status")


def test_unknown_game_uid_raises_router_error():
    """Unknown game_uid must raise RouterError."""
    r, cop, thief = make_router()
    with pytest.raises(RouterError):
        r.route("UNKNOWN", 1, "get_status", {})


def test_sub_game_out_of_range_raises():
    """Sub-game number 0 or 7+ must raise RouterError."""
    r, cop, thief = make_router()
    with pytest.raises(RouterError):
        r.route("uid_codex_001", 7, "get_status", {})


def test_get_role_for_sub_game_returns_cop_on_odd():
    """get_role_for_sub_game must return 'cop' for sub-game 1."""
    r, cop, thief = make_router()
    assert r.get_role_for_sub_game("uid_codex_001", 1) == "cop"


def test_get_role_for_sub_game_returns_thief_on_even():
    """get_role_for_sub_game must return 'thief' for sub-game 2."""
    r, cop, thief = make_router()
    assert r.get_role_for_sub_game("uid_codex_001", 2) == "thief"


def test_all_six_sub_games_route_correctly():
    """Sub-games 1,3,5 → cop; 2,4,6 → thief for default schedule."""
    r, cop, thief = make_router()
    for sg in range(1, 7):
        r.route("uid_codex_001", sg, "get_status", {})
    assert len([c for c in cop.calls if c[0] == "get_status"]) == 3
    assert len([c for c in thief.calls if c[0] == "get_status"]) == 3
