"""Tests for Router — routing logic and validation."""

import pytest

from league_manager.router import Router, RouterError
from league_manager.tests.mock_worker import MockWorker


def make_router():
    """Create a test router with mock workers and a registered series."""
    cop = MockWorker(role="police")
    thief = MockWorker(role="thief")
    r = Router(cop_worker=cop, thief_worker=thief)
    r.register_series(game_uid="uid_router_001", starting_role="police")
    return r, cop, thief


def test_routes_to_cop_in_odd_sub_game():
    """Sub-game 1 (odd) should route to cop worker."""
    r, cop, thief = make_router()
    r.route("uid_router_001", 1, "get_status", {})
    cop.assert_called("get_status")


def test_routes_to_thief_in_even_sub_game():
    """Sub-game 2 (even) should route to thief worker."""
    r, cop, thief = make_router()
    r.route("uid_router_001", 2, "get_status", {})
    thief.assert_called("get_status")


def test_unknown_game_uid_raises():
    """Unknown game_uid must raise RouterError."""
    r, cop, thief = make_router()
    with pytest.raises(RouterError, match="unknown game_uid"):
        r.route("UNKNOWN_UID", 1, "get_status", {})


def test_sub_game_out_of_range_raises():
    """Sub-game number 7 is out of range and must raise RouterError."""
    r, cop, thief = make_router()
    with pytest.raises(RouterError):
        r.route("uid_router_001", 7, "get_status", {})


def test_all_six_sub_games_route():
    """Default schedule: sub-games 1,3,5 → cop; 2,4,6 → thief."""
    r, cop, thief = make_router()
    for sg in range(1, 7):
        r.route("uid_router_001", sg, "get_status", {})
    assert len([c for c in cop.calls if c[0] == "get_status"]) == 3
    assert len([c for c in thief.calls if c[0] == "get_status"]) == 3


def test_reversed_schedule_routes_correctly():
    """When starting_role=thief, sub-game 1 routes to thief worker."""
    cop = MockWorker(role="police")
    thief = MockWorker(role="thief")
    r = Router(cop_worker=cop, thief_worker=thief)
    r.register_series(game_uid="uid_router_002", starting_role="thief")
    r.route("uid_router_002", 1, "get_status", {})
    thief.assert_called("get_status")


def test_invalid_tool_raises():
    """Calling a tool that does not exist on the worker must raise RouterError."""
    r, cop, thief = make_router()
    with pytest.raises(RouterError, match="no tool"):
        r.route("uid_router_001", 1, "nonexistent_tool", {})
